"""
A janela do programa.

Os métodos estão na mesma ordem em que a pessoa usa a tela: montar a janela,
escolher as pastas, analisar, receber os resultados, revisar a tabela, consultar
o painel lateral e, por fim, copiar. Quem for ler o código pode seguir de cima
para baixo como se estivesse usando o programa.
"""

import os
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, simpledialog, ttk

import config
from cache import Cache
from gemini_client import ClienteGemini, descrever_erro
from naming import finalizar_nome, montar_nome
from organizer import copiar
from pdf_tools import listar_pdfs, texto_preview
from pipeline import BAIXA, CACHE, ERRO, OK, Processador, Resultado
from schema import AREAS_SUGERIDAS, TIPOS

# Dois estados que só existem na tela (os outros vêm do pipeline).
NA_FILA, CANCELADO = "fila", "cancelado"

ICONES = {OK: "✔", CACHE: "↺", BAIXA: "⚠", ERRO: "✖", NA_FILA: "⏳", CANCELADO: "⏹"}

# (id, título, largura, pode editar?)
COLUNAS = [
    ("status", "", 34, False),
    ("arquivo", "Arquivo original", 190, False),
    ("tipo", "Categoria", 120, True),
    ("area", "Área", 110, True),
    ("sobrenome", "Sobrenome", 100, True),
    ("ano", "Ano", 50, True),
    ("titulo", "Título", 260, True),
    ("novo_nome", "Novo nome (duplo clique edita)", 330, True),
    ("conf", "Conf.", 50, False),
]

TEXTO_INICIAL = (
    "Como usar:\n"
    "1. Escolha a pasta dos PDFs (qualquer pasta do computador).\n"
    "2. Clique em ▶ Analisar com IA.\n"
    "3. Revise a tabela. Duplo clique edita uma célula; Delete tira a linha.\n"
    "   ⚠ amarelo = a IA ficou em dúvida; ✖ vermelho = erro; ↺ = veio do cache.\n"
    "4. Clique em Copiar e renomear. Os originais nunca são alterados.\n\n"
    "Campos do modelo de nome: {area} {sobrenome} {ano} {titulo} {tipo}"
)

# De quanto em quanto tempo a janela recolhe as novidades das threads.
INTERVALO_MS = 150


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Renomeador de PDFs acadêmicos — Gemini")
        root.geometry("1500x760")
        root.minsize(1000, 500)

        self.cfg = config.carregar()
        self.cache = Cache(config.PASTA_CACHE / "analises.sqlite")
        self.cliente: ClienteGemini | None = None    # criado na primeira análise
        self.processador: Processador | None = None

        # Cada linha da tabela tem um dicionário com tudo o que sabemos dela.
        self.linhas: dict[str, dict] = {}            # id da linha -> dados
        self.linha_do_arquivo: dict[Path, str] = {}  # caminho -> id da linha

        # As threads de fundo não tocam na janela; elas deixam recados aqui.
        self.eventos: Queue = Queue()
        self.geracao = 0          # número da rodada atual de análise
        self.total = 0
        self.feitos = 0
        self.ultimo_aviso = ""

        self.var_origem = tk.StringVar()
        self.var_destino = tk.StringVar()
        self.var_subpastas = tk.BooleanVar(value=False)
        self.var_modelo_nome = tk.StringVar(value=self.cfg.modelo_nome)
        self.var_status = tk.StringVar(value="Escolha a pasta com os PDFs.")

        self._montar_topo()
        self._montar_centro()
        self._montar_rodape()
        self.root.after(INTERVALO_MS, self._recolher_eventos)

    # ==================================================================
    # 1. Montagem da janela
    # ==================================================================

    def _montar_topo(self):
        topo = ttk.Frame(self.root, padding=(10, 8, 10, 0))
        topo.pack(fill=tk.X)
        topo.columnconfigure(1, weight=1)

        ttk.Label(topo, text="Pasta dos PDFs:").grid(row=0, column=0, sticky="w")
        ttk.Entry(topo, textvariable=self.var_origem).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(topo, text="Escolher…", command=self.escolher_origem).grid(row=0, column=2)
        ttk.Checkbutton(topo, text="Incluir subpastas",
                        variable=self.var_subpastas).grid(row=0, column=3, padx=8)
        self.botao_analisar = ttk.Button(topo, text="▶ Analisar com IA", command=self.analisar)
        self.botao_analisar.grid(row=0, column=4, padx=(8, 0))
        self.botao_cancelar = ttk.Button(topo, text="■ Cancelar", command=self.cancelar,
                                         state=tk.DISABLED)
        self.botao_cancelar.grid(row=0, column=5, padx=4)

        ttk.Label(topo, text="Pasta de saída:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(topo, textvariable=self.var_destino).grid(row=1, column=1, sticky="ew",
                                                            padx=5, pady=(6, 0))
        ttk.Button(topo, text="Escolher…", command=self.escolher_destino).grid(
            row=1, column=2, pady=(6, 0))
        ttk.Label(topo, text="Modelo do nome:").grid(row=1, column=3, sticky="e", pady=(6, 0))
        campo_modelo = ttk.Entry(topo, textvariable=self.var_modelo_nome, width=34)
        campo_modelo.grid(row=1, column=4, columnspan=2, sticky="ew", pady=(6, 0))
        campo_modelo.bind("<Return>", lambda _: self.reaplicar_modelo())
        campo_modelo.bind("<FocusOut>", lambda _: self.reaplicar_modelo())

    def _montar_centro(self):
        divisoria = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        divisoria.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        divisoria.add(self._montar_tabela(divisoria), weight=4)
        divisoria.add(self._montar_painel(divisoria), weight=2)

    def _montar_tabela(self, pai):
        quadro = ttk.Frame(pai)
        self.tabela = ttk.Treeview(quadro, columns=[c[0] for c in COLUNAS],
                                   show="headings", selectmode="extended")
        for coluna, titulo, largura, _ in COLUNAS:
            self.tabela.heading(coluna, text=titulo, command=lambda c=coluna: self.ordenar(c))
            self.tabela.column(coluna, width=largura, minwidth=30,
                               stretch=coluna in ("titulo", "novo_nome"),
                               anchor="center" if coluna in ("status", "ano", "conf") else "w")

        self.tabela.tag_configure(BAIXA, background="#fff4c2")
        self.tabela.tag_configure(ERRO, background="#f8d7da")
        self.tabela.tag_configure(CACHE, foreground="#375a7f")
        self.tabela.tag_configure(NA_FILA, foreground="#888888")
        self.tabela.tag_configure(CANCELADO, foreground="#888888")

        rolagem_v = ttk.Scrollbar(quadro, orient=tk.VERTICAL, command=self.tabela.yview)
        rolagem_h = ttk.Scrollbar(quadro, orient=tk.HORIZONTAL, command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=rolagem_v.set, xscrollcommand=rolagem_h.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        rolagem_v.grid(row=0, column=1, sticky="ns")
        rolagem_h.grid(row=1, column=0, sticky="ew")
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        self.tabela.bind("<Double-1>", self.editar_celula)
        self.tabela.bind("<<TreeviewSelect>>", lambda _: self.mostrar_detalhes())
        self.tabela.bind("<Delete>", lambda _: self.remover_selecionados())
        return quadro

    def _montar_painel(self, pai):
        quadro = ttk.Frame(pai, padding=(6, 0, 0, 0))
        botoes = ttk.Frame(quadro)
        botoes.pack(fill=tk.X)
        ttk.Button(botoes, text="📄 Abrir PDF", command=self.abrir_pdf).pack(side=tk.LEFT)
        ttk.Button(botoes, text="Ver texto", command=self.ver_texto).pack(side=tk.LEFT, padx=4)
        ttk.Button(botoes, text="↻ Reanalisar com instrução…",
                   command=self.reanalisar_com_instrucao).pack(side=tk.LEFT)

        self.painel = tk.Text(quadro, wrap="word", font=("Consolas", 10), padx=6, pady=6)
        rolagem = ttk.Scrollbar(quadro, command=self.painel.yview)
        self.painel.configure(yscrollcommand=rolagem.set)
        rolagem.pack(side=tk.RIGHT, fill=tk.Y, pady=(6, 0))
        self.painel.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self._escrever_no_painel(TEXTO_INICIAL)
        return quadro

    def _montar_rodape(self):
        rodape = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        rodape.pack(fill=tk.X)
        self.progresso = ttk.Progressbar(rodape, mode="determinate", length=260)
        self.progresso.pack(side=tk.LEFT)
        ttk.Label(rodape, textvariable=self.var_status).pack(side=tk.LEFT, padx=10)
        self.botao_copiar = ttk.Button(rodape, text="✔ Copiar e renomear",
                                       command=self.copiar)
        self.botao_copiar.pack(side=tk.RIGHT)

    # ==================================================================
    # 2. Escolha das pastas
    # ==================================================================

    def escolher_origem(self):
        pasta = filedialog.askdirectory(title="Pasta com os PDFs",
                                        initialdir=self.var_origem.get() or None)
        if not pasta:
            return
        self.var_origem.set(os.path.normpath(pasta))
        # Sugere uma saída ao lado dos originais, mas só se o usuário ainda não escolheu.
        if not self.var_destino.get():
            self.var_destino.set(os.path.normpath(os.path.join(pasta, "out")))

    def escolher_destino(self):
        pasta = filedialog.askdirectory(title="Pasta de saída",
                                        initialdir=self.var_destino.get() or None)
        if pasta:
            self.var_destino.set(os.path.normpath(pasta))

    # ==================================================================
    # 3. Análise
    # ==================================================================

    def analisar(self):
        origem = Path(self.var_origem.get().strip())
        if not origem.is_dir():
            messagebox.showwarning("Pasta", "Escolha uma pasta válida com PDFs.")
            return
        if not self.var_destino.get().strip():
            self.var_destino.set(str(origem / "out"))
        destino = Path(self.var_destino.get().strip())

        pdfs = listar_pdfs(origem, self.var_subpastas.get(), ignorar=destino)
        if not pdfs:
            messagebox.showinfo("Nada a fazer", "Nenhum PDF encontrado nessa pasta.")
            return

        # A tabela aparece cheia na hora, com tudo em ⏳; os resultados vão preenchendo.
        self.tabela.delete(*self.tabela.get_children())
        self.linhas.clear()
        self.linha_do_arquivo.clear()
        for pdf in pdfs:
            nome_exibido = pdf.relative_to(origem) if self.var_subpastas.get() else pdf.name
            id_linha = self.tabela.insert("", tk.END, tags=(NA_FILA,), values=(
                ICONES[NA_FILA], str(nome_exibido), "", "", "", "", "", "", ""))
            self.linhas[id_linha] = {"caminho": pdf, "status": NA_FILA,
                                     "manual": False, "campos": {}}
            self.linha_do_arquivo[pdf] = id_linha

        self._iniciar_rodada(pdfs)

    def _iniciar_rodada(self, caminhos, instrucoes=None, forcar=False):
        """Começa uma rodada de análise sem travar a janela."""
        self.cfg = config.carregar()   # relê o .env: a pessoa pode ter mudado algo
        self.geracao += 1
        rodada = self.geracao
        self.total, self.feitos = len(caminhos), 0
        self.ultimo_aviso = ""
        self.progresso.configure(maximum=self.total, value=0)
        self._modo_ocupado(True)
        self.var_status.set("Conectando ao Gemini…")

        def conectar_e_comecar():
            # Roda fora da thread da janela, então só conversa com ela pela fila.
            try:
                if self.cliente is None:
                    cliente = ClienteGemini(self.cfg.api_key, self.cfg.modelo, self.cfg.rpm,
                                            memoria=config.PASTA_CACHE / "ultimo_modelo.txt")
                    cliente.resolver_modelo()
                    self.cliente = cliente
                if rodada != self.geracao:
                    return   # a pessoa cancelou enquanto a gente conectava
                processador = Processador(self.cliente, self.cache, self.cfg.paginas,
                                          self.cfg.workers, self.eventos, rodada)
                self.processador = processador
                processador.iniciar(caminhos, instrucoes, forcar)
            except Exception as erro:
                self.eventos.put((rodada, "falha_inicio", descrever_erro(erro)))

        threading.Thread(target=conectar_e_comecar, daemon=True).start()

    def cancelar(self):
        """
        Devolve a janela na hora. Chamadas que já estavam no ar não têm como ser
        interrompidas; elas terminam em segundo plano e, se chegarem, o resultado
        é aproveitado (já foi pago, afinal).
        """
        if self.processador:
            self.processador.cancelar()
        self.geracao += 1
        quantos = self._marcar_pendentes_como_cancelados()
        self._modo_ocupado(False)
        self.var_status.set(
            f"Cancelado. {quantos} arquivo(s) não analisado(s) (⏹). Para retomar, "
            f"selecione-os e use Reanalisar, ou clique em Analisar de novo "
            f"(o que já foi feito vem do cache).")

    # ==================================================================
    # 4. Recebendo os resultados
    # ==================================================================

    def _recolher_eventos(self):
        """
        Roda a cada INTERVALO_MS na thread da janela. É o único lugar onde o que
        acontece nas threads de fundo chega à tela.
        """
        try:
            while True:
                rodada, tipo, carga = self.eventos.get_nowait()
                if tipo == "resultado":
                    # Mesmo de uma rodada cancelada, um resultado pronto vale a pena mostrar.
                    self._aplicar_resultado(carga, contar=rodada == self.geracao)
                elif rodada != self.geracao:
                    continue   # aviso velho de uma rodada que já foi cancelada
                elif tipo == "aviso":
                    self.ultimo_aviso = carga
                elif tipo == "falha_inicio":
                    self._falha_ao_conectar(carga)
                elif tipo == "fim":
                    self._modo_ocupado(False)
                    self.var_status.set(f"Concluído: {self.feitos}/{self.total}  ·  "
                                        + self._resumo_de_uso())
        except Empty:
            pass

        if self._esta_rodando() and self.cliente:
            aviso = f"   ·   ⚠ {self.ultimo_aviso}" if self.ultimo_aviso else ""
            self.var_status.set(
                f"Analisando {self.feitos}/{self.total} com {self.cliente.modelo}…{aviso}")
        self.root.after(INTERVALO_MS, self._recolher_eventos)

    def _aplicar_resultado(self, resultado: Resultado, contar: bool = True):
        if contar:
            self.feitos += 1
            self.progresso.configure(value=self.feitos)

        id_linha = self.linha_do_arquivo.get(resultado.caminho)
        if not id_linha or not self.tabela.exists(id_linha):
            return   # a pessoa tirou a linha da lista enquanto esperava

        linha = self.linhas[id_linha]
        linha.update(status=resultado.status, dados=resultado.dados,
                     erro=resultado.erro, manual=False)
        dados = resultado.dados
        if dados:
            linha["campos"] = {"tipo": dados.tipo_documento.value, "area": dados.area,
                               "sobrenome": dados.sobrenome_principal,
                               "ano": str(dados.ano or ""), "titulo": dados.titulo}
        else:
            linha["campos"] = {"tipo": "Outros", "area": "", "sobrenome": "",
                               "ano": "", "titulo": ""}
            linha["novo_nome"] = resultado.caminho.name

        self._redesenhar_linha(id_linha)
        if id_linha in self.tabela.selection():
            self.mostrar_detalhes()

    def _falha_ao_conectar(self, mensagem):
        self._modo_ocupado(False)
        self._marcar_pendentes_como_cancelados()
        self.var_status.set("Não foi possível conectar.")
        messagebox.showerror("Gemini", f"{mensagem}\n\nConfira GEMINI_API_KEY no arquivo .env.")

    def _resumo_de_uso(self) -> str:
        c = self.cliente
        if not c:
            return ""
        return f"modelo {c.modelo}  ·  {c.chamadas} chamadas  ·  {c.tokens_usados:,} tokens"

    def _marcar_pendentes_como_cancelados(self) -> int:
        quantos = 0
        for id_linha, linha in self.linhas.items():
            if linha["status"] == NA_FILA:
                linha["status"] = CANCELADO
                self.tabela.set(id_linha, "status", ICONES[CANCELADO])
                quantos += 1
        return quantos

    def _modo_ocupado(self, ocupado: bool):
        self.botao_analisar.configure(state=tk.DISABLED if ocupado else tk.NORMAL)
        self.botao_copiar.configure(state=tk.DISABLED if ocupado else tk.NORMAL)
        self.botao_cancelar.configure(state=tk.NORMAL if ocupado else tk.DISABLED)

    def _esta_rodando(self) -> bool:
        return str(self.botao_cancelar["state"]) == tk.NORMAL

    # ==================================================================
    # 5. Revisão na tabela
    # ==================================================================

    def _redesenhar_linha(self, id_linha):
        """Recalcula o novo nome (se não foi editado à mão) e atualiza a linha na tela."""
        linha = self.linhas[id_linha]
        campos = linha["campos"]
        if not linha["manual"] and linha["status"] != ERRO:
            linha["novo_nome"] = montar_nome(self.var_modelo_nome.get(), campos)

        confianca = f"{linha['dados'].confianca:.0%}" if linha.get("dados") else ""
        valores = list(self.tabela.item(id_linha, "values"))
        valores[0] = ICONES.get(linha["status"], "")
        valores[2:9] = [campos.get("tipo", ""), campos.get("area", ""),
                        campos.get("sobrenome", ""), campos.get("ano", ""),
                        campos.get("titulo", ""), linha.get("novo_nome", ""), confianca]
        self.tabela.item(id_linha, values=valores, tags=(linha["status"],))

    def reaplicar_modelo(self):
        for id_linha, linha in self.linhas.items():
            if linha["campos"]:
                self._redesenhar_linha(id_linha)

    def editar_celula(self, evento):
        """Duplo clique: põe um campo de texto (ou lista) por cima da célula."""
        if self.tabela.identify_region(evento.x, evento.y) != "cell":
            return
        id_linha = self.tabela.identify_row(evento.y)
        indice = int(self.tabela.identify_column(evento.x)[1:]) - 1
        coluna, _, _, editavel = COLUNAS[indice]
        if not editavel or id_linha not in self.linhas or not self.linhas[id_linha]["campos"]:
            return

        x, y, largura, altura = self.tabela.bbox(id_linha, f"#{indice + 1}")
        valor_atual = self.tabela.set(id_linha, coluna)

        if coluna == "tipo":
            editor = ttk.Combobox(self.tabela, values=TIPOS, state="readonly")
            editor.set(valor_atual)
        elif coluna == "area":
            # Área aceita texto livre: a lista é só sugestão.
            editor = ttk.Combobox(self.tabela, values=AREAS_SUGERIDAS)
            editor.set(valor_atual)
        else:
            editor = ttk.Entry(self.tabela)
            editor.insert(0, valor_atual)
            editor.select_range(0, tk.END)
        editor.place(x=x, y=y, width=max(largura, 160), height=altura)
        editor.focus_set()

        def salvar(_=None):
            if not editor.winfo_exists():
                return
            valor = editor.get().strip()
            editor.destroy()
            linha = self.linhas[id_linha]
            if coluna == "novo_nome":
                # Nome digitado à mão vira lei: o modelo de nome não mexe mais nele.
                linha["novo_nome"] = finalizar_nome(valor)
                linha["manual"] = True
            else:
                linha["campos"][coluna] = valor
            self._redesenhar_linha(id_linha)

        editor.bind("<Return>", salvar)
        editor.bind("<FocusOut>", salvar)
        editor.bind("<Escape>", lambda _: editor.destroy())
        if isinstance(editor, ttk.Combobox):
            editor.bind("<<ComboboxSelected>>", salvar)

    def ordenar(self, coluna, decrescente=False):
        itens = [(self.tabela.set(i, coluna).lower(), i) for i in self.tabela.get_children()]
        itens.sort(reverse=decrescente)
        for posicao, (_, id_linha) in enumerate(itens):
            self.tabela.move(id_linha, "", posicao)
        # O próximo clique no mesmo título inverte a ordem.
        self.tabela.heading(coluna, command=lambda: self.ordenar(coluna, not decrescente))

    def remover_selecionados(self):
        for id_linha in self.tabela.selection():
            self.tabela.delete(id_linha)
            linha = self.linhas.pop(id_linha)
            self.linha_do_arquivo.pop(linha["caminho"], None)

    # ==================================================================
    # 6. Painel lateral
    # ==================================================================

    def mostrar_detalhes(self):
        _, linha = self._linha_selecionada()
        if not linha:
            return
        partes = [f"Arquivo: {linha['caminho']}"]
        if linha.get("erro"):
            partes.append(f"\n✖ ERRO: {linha['erro']}")

        d = linha.get("dados")
        if d:
            autores = "; ".join(f"{a.nome} {a.sobrenome}" for a in d.autores) or "—"
            partes += [
                f"\nTítulo: {d.titulo}" + (f" — {d.subtitulo}" if d.subtitulo else ""),
                f"Autores: {autores}",
                f"Ano: {d.ano or '—'}    Tipo: {d.tipo_documento.value}    "
                f"Idioma: {d.idioma or '—'}",
                f"Área: {d.area}" + (f" / {d.subarea}" if d.subarea else ""),
                f"Instituição: {d.instituicao or '—'}",
                f"Periódico: {d.periodico or '—'}",
                f"DOI: {d.doi or '—'}",
                f"Palavras-chave: {', '.join(d.palavras_chave) or '—'}",
                f"Confiança: {d.confianca:.0%}",
                f"\nResumo: {d.resumo_curto}",
            ]
        self._escrever_no_painel("\n".join(partes))

    def abrir_pdf(self):
        _, linha = self._linha_selecionada()
        if linha:
            os.startfile(linha["caminho"])

    def ver_texto(self):
        _, linha = self._linha_selecionada()
        if linha:
            self._escrever_no_painel(texto_preview(linha["caminho"]))

    def reanalisar_com_instrucao(self):
        selecionadas = [i for i in self.tabela.selection() if i in self.linhas]
        if not selecionadas:
            messagebox.showinfo("Reanalisar", "Selecione uma ou mais linhas na tabela.")
            return
        if self._esta_rodando():
            messagebox.showinfo("Aguarde", "Espere a análise atual terminar.")
            return

        instrucao = simpledialog.askstring(
            "Reanalisar", "Instrução para a IA (opcional), ex.:\n"
            "'o autor é João Pereira'  ·  'é uma dissertação de 2019'  ·  'área: Enfermagem'",
            parent=self.root)
        if instrucao is None:
            return   # clicou em Cancelar na caixinha

        caminhos = []
        for id_linha in selecionadas:
            linha = self.linhas[id_linha]
            linha["status"] = NA_FILA
            self.tabela.item(id_linha, tags=(NA_FILA,))
            self.tabela.set(id_linha, "status", ICONES[NA_FILA])
            caminhos.append(linha["caminho"])
        self._iniciar_rodada(caminhos, {c: instrucao.strip() for c in caminhos}, forcar=True)

    def _linha_selecionada(self):
        selecao = self.tabela.selection()
        if selecao and selecao[0] in self.linhas:
            return selecao[0], self.linhas[selecao[0]]
        return None, None

    def _escrever_no_painel(self, texto):
        self.painel.delete("1.0", tk.END)
        self.painel.insert(tk.END, texto)

    # ==================================================================
    # 7. Cópia final
    # ==================================================================

    def copiar(self):
        destino = Path(self.var_destino.get().strip() or ".")
        itens, pulados = [], 0
        for id_linha in self.tabela.get_children():
            linha = self.linhas[id_linha]
            # Sem análise não há nome confiável, a menos que a pessoa tenha digitado um.
            sem_nome = linha["status"] in (NA_FILA, CANCELADO) or \
                (linha["status"] == ERRO and not linha["manual"])
            if sem_nome:
                pulados += 1
                continue
            categoria = linha["campos"].get("tipo") or "Outros"
            itens.append((linha["caminho"], categoria, linha["novo_nome"]))

        if not itens:
            messagebox.showwarning("Atenção", "Nenhum arquivo pronto para copiar.")
            return

        aviso = (f"\n\n{pulados} arquivo(s) com erro ou pendentes serão pulados "
                 f"(edite o novo nome deles para incluí-los).") if pulados else ""
        confirmou = messagebox.askyesno(
            "Confirmar", f"Copiar {len(itens)} PDF(s) para:\n{destino}\n\n"
                         f"Subpastas por categoria. Originais não são alterados.{aviso}")
        if not confirmou:
            return

        resultado = copiar(itens, destino)
        mensagem = (f"Copiados: {len(resultado['copiados'])}\n"
                    f"Erros: {len(resultado['erros'])}")
        if resultado["erros"]:
            mensagem += "\n\n" + "\n".join(f"• {Path(e['origem']).name}: {e['erro']}"
                                           for e in resultado["erros"][:8])
        if resultado["log"]:
            mensagem += f"\n\nRegistro: {resultado['log']}"
        messagebox.showinfo("Resultado", mensagem)

        if resultado["copiados"] and messagebox.askyesno("Abrir", "Abrir a pasta de saída?"):
            os.startfile(destino)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")   # visual nativo do Windows
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
