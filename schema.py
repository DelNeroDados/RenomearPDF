"""
O formato exato da resposta que pedimos ao Gemini.

Esta classe é enviada junto com o pedido (saída estruturada), e o Gemini é
obrigado a devolver um JSON que encaixa nela. As descrições de cada campo
funcionam como instruções: é por elas que a IA sabe, por exemplo, que numa
tese o autor é o aluno e não o orientador.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    ARTIGO = "Artigos"
    TESE = "Teses"
    DISSERTACAO = "Dissertações"
    MONOGRAFIA = "Monografias e TCCs"
    LIVRO = "Livros"
    CAPITULO = "Capítulos"
    SLIDES = "Slides e Apresentações"
    APOSTILA = "Apostilas e Material Didático"
    OUTRO = "Outros"


TIPOS = [t.value for t in TipoDocumento]

AREAS_SUGERIDAS = [
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
    tipo_documento: TipoDocumento
    area: str = Field(description=(
        "Grande área do conhecimento em português, preferindo uma destas: "
        + ", ".join(AREAS_SUGERIDAS)
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
