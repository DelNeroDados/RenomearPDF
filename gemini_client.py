"""
Tudo o que fala com o Gemini mora aqui.

A ideia é que o resto do programa só precise chamar `cliente.analisar(info)` e
receber de volta um `MetadadosPDF` pronto. Os detalhes chatos ficam escondidos
neste arquivo: respeitar a cota, tentar de novo quando o Google está
sobrecarregado e trocar de modelo quando um deles para de responder.
"""

import re
import threading
import time

import httpx
from google import genai
from google.genai import errors, types

from pdf_tools import InfoPDF
from schema import MetadadosPDF

# Erros que valem uma nova tentativa. O resto (chave errada, pedido malformado)
# não melhora com insistência, então desistimos na hora.
ERROS_PASSAGEIROS = {408, 429, 500, 502, 503, 504}

# Teto de tentativas por PDF, somando todos os modelos tentados.
MAX_TENTATIVAS = 8

# Sem isto, uma conexão que trava pode prender uma thread para sempre.
TIMEOUT_MS = 120_000

INSTRUCOES = """Você cataloga documentos acadêmicos para uma biblioteca pessoal.
Recebe as primeiras páginas de um PDF (capa, folha de rosto, ficha catalográfica,
resumo) e devolve os metadados no formato pedido.

Regras:
- Use o que está escrito no documento; não invente. Campo desconhecido = null.
- Título: o da obra, não o do periódico nem o do capítulo do sumário.
- Teses/dissertações/TCC: autor é o discente; orientador não entra em autores.
- Slides de aula, apostilas e notas de curso não são artigos.
- Os metadados embutidos e o nome do arquivo são só pistas e costumam estar errados.
- Se o documento for ilegível, preencha o que conseguir e use confianca baixa."""


class Cancelado(Exception):
    """O usuário clicou em Cancelar enquanto a gente esperava."""


class ClienteGemini:
    def __init__(self, api_key: str, modelo: str = "", rpm: int = 10, memoria=None):
        """
        modelo:  vazio deixa o programa escolher sozinho.
        rpm:     quantas chamadas por minuto a chave aguenta.
        memoria: arquivo onde anotamos o último modelo que funcionou, para começar
                 por ele da próxima vez em vez de bater de novo num que estava sem cota.
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY não configurada no .env")

        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self.modelo = modelo
        self.candidatos: list[str] = [modelo] if modelo else []
        self.memoria = memoria
        self.limitador = LimitadorTaxa(rpm)

        # Contadores mostrados na barra de status ao final.
        self.chamadas = 0
        self.tokens_usados = 0

        # A interface substitui esta função para exibir avisos ("trocando de modelo...").
        self.ao_aviso = lambda mensagem: None

        self._trava = threading.Lock()
        self._ultimo_anotado = ""

    # ------------------------------------------------------------------
    # Escolha do modelo
    # ------------------------------------------------------------------

    def resolver_modelo(self) -> str:
        """
        Confere se a chave funciona e monta a fila de modelos que vamos tentar.

        Ordem da fila: o modelo fixado no .env (se houver), depois o último que deu
        certo, depois os Flash do mais novo para o mais velho. Listar modelos não
        consome cota, então isto pode rodar sempre que o programa abre.
        """
        disponiveis = [
            m.name.removeprefix("models/")
            for m in self.client.models.list()
            if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"])
        ]
        if self.modelo and self.modelo not in disponiveis:
            raise ValueError(f"Modelo '{self.modelo}' não disponível para esta chave.")

        fila = ordenar_flash(disponiveis)
        ultimo = self._ler_memoria()
        if ultimo in fila:
            fila.remove(ultimo)
            fila.insert(0, ultimo)

        fixado = [self.modelo] if self.modelo else []
        self.candidatos = fixado + [m for m in fila if m != self.modelo]
        if not self.candidatos:
            raise ValueError("Nenhum modelo Flash disponível para esta chave.")

        self.modelo = self.candidatos[0]
        return self.modelo

    # ------------------------------------------------------------------
    # Análise de um PDF
    # ------------------------------------------------------------------

    def analisar(self, info: InfoPDF, instrucao_extra: str = "",
                 cancelado: threading.Event | None = None) -> MetadadosPDF:
        """
        Manda as primeiras páginas do PDF e devolve os metadados.

        Preferimos enviar o próprio PDF (o Gemini enxerga layout e lê páginas
        escaneadas). Se o Gemini recusar o arquivo, caímos para o texto extraído.
        """
        pistas = self._montar_pistas(info, instrucao_extra)

        if info.recorte:
            pdf = types.Part.from_bytes(data=info.recorte, mime_type="application/pdf")
            try:
                return self._chamar([pdf, pistas], cancelado)
            except errors.ClientError as erro:
                if erro.code != 400 or not info.texto.strip():
                    raise
                # 400 aqui quase sempre é PDF que o Gemini não conseguiu abrir.

        if not info.texto.strip():
            raise ValueError("PDF sem texto e sem páginas enviáveis")
        texto = f"{pistas}\n\nTexto das primeiras páginas:\n{info.texto[:20000]}"
        return self._chamar([texto], cancelado)

    def _montar_pistas(self, info: InfoPDF, instrucao_extra: str) -> str:
        pistas = [f"Nome do arquivo: {info.caminho.name}",
                  f"Total de páginas: {info.paginas}"]
        if info.titulo_meta:
            pistas.append(f"Título nos metadados: {info.titulo_meta}")
        if info.autor_meta:
            pistas.append(f"Autor nos metadados: {info.autor_meta}")
        if instrucao_extra:
            pistas.append(f"CORREÇÃO DO USUÁRIO (tem prioridade): {instrucao_extra}")
        return "\n".join(pistas)

    def _chamar(self, conteudo, cancelado) -> MetadadosPDF:
        """Faz a chamada de verdade, com novas tentativas e troca de modelo."""
        config = types.GenerateContentConfig(
            system_instruction=INSTRUCOES,
            response_mime_type="application/json",
            response_schema=MetadadosPDF,   # o Gemini é obrigado a seguir este formato
            temperature=0.1,                # catalogar não pede criatividade
        )
        falhas_neste_modelo = 0

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            self.limitador.aguardar(cancelado)
            modelo = self.modelo
            try:
                resposta = self.client.models.generate_content(
                    model=modelo, contents=conteudo, config=config)
                self._registrar_sucesso(modelo, resposta)
                return _ler_resposta(resposta)

            except ValueError:
                # Resposta fora do formato. Com saída estruturada é raro; tenta de novo.
                if tentativa == MAX_TENTATIVAS:
                    raise

            except (errors.APIError, httpx.TimeoutException, httpx.TransportError) as erro:
                if tentativa == MAX_TENTATIVAS:
                    raise
                falhas_neste_modelo += 1
                acao, espera = _decidir(erro, falhas_neste_modelo, tentativa)

                if acao == "desistir":
                    raise
                if acao == "trocar":
                    if not self._trocar_modelo(modelo, _motivo(erro)):
                        raise   # acabaram os modelos
                    falhas_neste_modelo = 0
                    continue

                # acao == "esperar"
                if _codigo(erro) == 429:
                    self.limitador.adiar(espera)   # segura todas as threads, não só esta
                self.ao_aviso(f"{modelo}: erro {_codigo(erro)}, "
                              f"tentando de novo em {espera:.0f}s")
                _dormir(espera, cancelado)

        raise RuntimeError("não deveria chegar aqui")

    def _registrar_sucesso(self, modelo: str, resposta) -> None:
        with self._trava:
            self.chamadas += 1
            uso = getattr(resposta, "usage_metadata", None)
            self.tokens_usados += getattr(uso, "total_token_count", 0) or 0
        self._anotar_memoria(modelo)

    def _trocar_modelo(self, que_falhou: str, motivo: str) -> bool:
        """
        Passa para o próximo modelo da fila. A troca vale para todas as threads:
        não adianta cada uma descobrir sozinha que o modelo está sem cota.
        """
        with self._trava:
            if self.modelo != que_falhou:
                return True   # outra thread já trocou enquanto esta esperava
            if que_falhou in self.candidatos:
                self.candidatos.remove(que_falhou)
            if not self.candidatos:
                return False
            self.modelo = self.candidatos[0]
        self.ao_aviso(f"{que_falhou} {motivo}; trocando para {self.modelo}")
        return True

    # ------------------------------------------------------------------
    # Memória do último modelo que funcionou
    # ------------------------------------------------------------------

    def _ler_memoria(self) -> str:
        if not self.memoria:
            return ""
        try:
            return self.memoria.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _anotar_memoria(self, modelo: str) -> None:
        if not self.memoria or modelo == self._ultimo_anotado:
            return
        try:
            self.memoria.parent.mkdir(parents=True, exist_ok=True)
            self.memoria.write_text(modelo, encoding="utf-8")
            self._ultimo_anotado = modelo
        except OSError:
            pass   # não conseguir anotar não deve atrapalhar a análise


# ----------------------------------------------------------------------
# Controle de cota
# ----------------------------------------------------------------------

class LimitadorTaxa:
    """
    Espaça as chamadas para não passar de `rpm` por minuto, somando todas as threads.

    Funciona como uma senha de padaria: cada chamada pega o próximo horário livre
    e espera até ele chegar.
    """

    def __init__(self, rpm: int):
        self.intervalo = 60.0 / max(1, rpm)
        self._proximo_horario = 0.0
        self._trava = threading.Lock()

    def aguardar(self, cancelado: threading.Event | None = None) -> None:
        with self._trava:
            agora = time.monotonic()
            espera = max(0.0, self._proximo_horario - agora)
            self._proximo_horario = max(agora, self._proximo_horario) + self.intervalo
        _dormir(espera, cancelado)

    def adiar(self, segundos: float) -> None:
        """Depois de um 429, empurra a fila inteira para frente."""
        with self._trava:
            self._proximo_horario = max(self._proximo_horario, time.monotonic() + segundos)


# ----------------------------------------------------------------------
# Decisões sobre erros
# ----------------------------------------------------------------------

def _decidir(erro, falhas_neste_modelo: int, tentativa: int) -> tuple[str, float]:
    """
    Diante de um erro, devolve ("desistir" | "trocar" | "esperar", segundos).

    - 404: o modelo foi desativado. Troca na hora.
    - 429 com espera longa ou limite diário: só volta amanhã. Troca na hora.
    - 503, timeout ou 429 curto: tenta o mesmo modelo mais uma vez; na segunda
      falha seguida, troca.
    - Qualquer outro erro (chave inválida etc.): desiste.
    """
    codigo = _codigo(erro)
    if codigo not in ERROS_PASSAGEIROS and codigo != 404:
        return "desistir", 0

    pedido = _retry_delay(erro)
    cota_longa = codigo == 429 and ((pedido or 0) > 30 or _cota_diaria(erro))
    if codigo == 404 or cota_longa or falhas_neste_modelo >= 2:
        return "trocar", 0

    return "esperar", min(pedido or 3 * tentativa, 30)


def _codigo(erro) -> int:
    # Timeout e queda de conexão não têm código HTTP; tratamos como 504.
    return erro.code if isinstance(erro, errors.APIError) else 504


def _motivo(erro) -> str:
    return {404: "indisponível", 429: "sem cota", 504: "sem resposta"}.get(
        _codigo(erro), "sobrecarregado")


def _retry_delay(erro) -> float | None:
    """Lê o 'retryDelay' que o Google às vezes manda junto com o erro (ex.: '37s')."""
    if not isinstance(erro, errors.APIError):
        return None
    try:
        for detalhe in (erro.details or {}).get("error", {}).get("details", []):
            if "retryDelay" in detalhe:
                return float(re.sub(r"[^\d.]", "", detalhe["retryDelay"]) or 0) or None
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def _cota_diaria(erro) -> bool:
    return isinstance(erro, errors.APIError) and "PerDay" in str(erro.details or "")


def descrever_erro(erro: Exception) -> str:
    """Transforma uma exceção em uma frase que faça sentido para quem usa o programa."""
    if isinstance(erro, errors.APIError):
        if erro.code in (401, 403):
            return f"Chave recusada ({erro.code}). Gere uma nova em aistudio.google.com/apikey."
        if erro.code == 429:
            if _cota_diaria(erro):
                return "Cota diária esgotada em todos os modelos (nível gratuito). Tente amanhã."
            return "Cota da API esgotada (429)."
        return f"Erro da API {erro.code}: {(erro.message or '')[:150]}"
    return f"{type(erro).__name__}: {str(erro)[:150]}"


# ----------------------------------------------------------------------
# Pequenos utilitários
# ----------------------------------------------------------------------

def _ler_resposta(resposta) -> MetadadosPDF:
    if isinstance(resposta.parsed, MetadadosPDF):
        return resposta.parsed
    return MetadadosPDF.model_validate_json(resposta.text)


def _dormir(segundos: float, cancelado: threading.Event | None) -> None:
    """Como time.sleep, mas acorda na hora se o usuário cancelar."""
    if segundos <= 0:
        return
    if cancelado is None:
        time.sleep(segundos)
    elif cancelado.wait(segundos):
        raise Cancelado()


def ordenar_flash(nomes: list[str]) -> list[str]:
    """
    Monta a fila de modelos Flash de texto, do mais forte para o mais fraco:
    versões estáveis (mais nova primeiro), o apelido '-latest' e, por último,
    as versões 'lite'. Previews e modelos de imagem ou voz ficam de fora.
    """
    def por_versao(sufixo):
        achados = []
        for nome in nomes:
            m = re.fullmatch(rf"gemini-(\d+(?:\.\d+)?)-{sufixo}", nome)
            if m:
                achados.append((float(m.group(1)), nome))
        return [nome for _, nome in sorted(achados, reverse=True)]

    fila = por_versao("flash")
    if "gemini-flash-latest" in nomes:
        fila.append("gemini-flash-latest")
    fila += por_versao("flash-lite")
    if "gemini-flash-lite-latest" in nomes:
        fila.append("gemini-flash-lite-latest")
    return fila


def escolher_flash(nomes: list[str]) -> str | None:
    fila = ordenar_flash(nomes)
    return fila[0] if fila else None
