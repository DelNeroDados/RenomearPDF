"""
O formato exato da resposta que pedimos ao Gemini.

Esta classe é enviada junto com o pedido (saída estruturada), e o Gemini é
obrigado a devolver um JSON que encaixa nela. As descrições de cada campo
funcionam como instruções: é por elas que a IA sabe, por exemplo, que numa
tese o autor é o aluno e não o orientador.
"""

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, create_model

# As listas que vêm com o programa. A pessoa pode mudá-las pelo menu
# Configurações; o que ela escolher fica em listas.json (veja listas.py).
CATEGORIAS_PADRAO = [
    "Artigos", "Teses", "Dissertações", "Monografias e TCCs", "Livros", "Capítulos",
    "Slides e Apresentações", "Apostilas e Material Didático", "Outros",
]

# Categoria de reserva: sempre existe, para quando nenhuma outra servir.
OUTROS = "Outros"

AREAS_PADRAO = [
    "Física", "Química", "Biologia", "Matemática", "Computação", "Engenharia",
    "Medicina", "Enfermagem", "Odontologia", "Saúde Pública", "Psicologia",
    "Educação", "Ensino de Ciências", "Filosofia", "História", "Sociologia",
    "Antropologia", "Política", "Direito", "Economia", "Administração",
    "Linguística", "Letras", "Artes", "Comunicação", "Geografia", "Agronomia",
]


class Autor(BaseModel):
    nome: str = Field(description="Prenomes do autor, ex.: 'Maria Clara'")
    sobrenome: str = Field(description="Último sobrenome, ex.: 'Silva'")


class MetadadosPDF(BaseModel):
    titulo: str = Field(description=(
        "Título real da obra, sem subtítulo. Use maiúscula só na primeira letra "
        "e em nomes próprios e siglas (ex.: 'Ensino de física quântica no Brasil')."
    ))
    subtitulo: Optional[str] = Field(default=None, description="Subtítulo, se houver")
    autores: list[Autor] = Field(description=(
        "Autores na ordem da obra. Em teses e dissertações, o autor é o discente, "
        "não o orientador. Lista vazia se não for possível identificar."
    ))
    ano: Optional[int] = Field(default=None, description="Ano de publicação ou defesa")
    # Aqui é texto livre, para o cache continuar valendo se a lista de categorias
    # mudar. Quem prende a IA às categorias atuais é esquema_para_ia(), lá embaixo.
    tipo_documento: str = Field(description="Categoria do documento")
    area: str = Field(description=(
        "Grande área do conhecimento em português, preferindo uma destas: "
        + ", ".join(AREAS_PADRAO)
    ))
    subarea: Optional[str] = None
    idioma: Optional[str] = Field(default=None, description="Ex.: 'português', 'inglês'")
    instituicao: Optional[str] = None
    periodico: Optional[str] = Field(default=None, description="Revista ou evento, se for artigo")
    doi: Optional[str] = None
    palavras_chave: list[str] = Field(default_factory=list)
    resumo_curto: str = Field(description="Resumo de 1 a 2 frases em português")
    confianca: float = Field(description=(
        "De 0 a 1: quão seguro você está de título, autor e ano. "
        "Use menos de 0.6 se o texto estiver ilegível ou ambíguo."
    ))

    @property
    def sobrenome_principal(self) -> str:
        return self.autores[0].sobrenome if self.autores else ""

    @property
    def autor_exibicao(self) -> str:
        if not self.autores:
            return ""
        a = self.autores[0]
        extra = f" et al. (+{len(self.autores) - 1})" if len(self.autores) > 1 else ""
        return f"{a.nome} {a.sobrenome}".strip() + extra


@lru_cache(maxsize=8)
def esquema_para_ia(categorias: tuple, areas: tuple) -> type[MetadadosPDF]:
    """
    O formato enviado ao Gemini, montado com as listas atuais da pessoa.

    A categoria vira uma lista fechada (enum): a IA é obrigada a escolher uma
    delas. A lista de áreas entra só como sugestão, na descrição do campo.
    """
    Categoria = Enum("Categoria", {f"C{i}": c for i, c in enumerate(categorias)}, type=str)
    return create_model(
        "MetadadosPDF", __base__=MetadadosPDF,
        tipo_documento=(Categoria, Field(description="Categoria do documento")),
        area=(str, Field(description="Grande área do conhecimento em português, "
                                     "preferindo uma destas: " + ", ".join(areas))),
    )


def para_texto_simples(dados: MetadadosPDF, categorias) -> MetadadosPDF:
    """Converte a resposta para o MetadadosPDF comum, com a categoria como texto."""
    bruto = dados.model_dump(mode="json")
    if bruto["tipo_documento"] not in categorias:
        bruto["tipo_documento"] = OUTROS
    return MetadadosPDF.model_validate(bruto)
