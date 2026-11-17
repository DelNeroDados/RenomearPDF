"""
As janelas do menu Configurações: editar uma lista (categorias ou áreas) e
trocar a chave da API.
"""

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from google import genai

import config
import pythons
from schema import OUTROS


class EditorLista(tk.Toplevel):
    """
    Uma lista editável: adicionar, remover, mudar a ordem, voltar ao padrão.
    Ao salvar, chama ao_salvar(nova_lista).
    """

    def __init__(self, pai, titulo, explicacao, itens, padrao, ao_salvar,
                 fixos=(), ordenar=False):
        super().__init__(pai)
        self.title(titulo)
        self.transient(pai)
        self.resizable(False, True)
        self.padrao, self.ao_salvar = list(padrao), ao_salvar
        self.fixos = {f.casefold() for f in fixos}
        self.ordenar = ordenar

        quadro = ttk.Frame(self, padding=12)
        quadro.pack(fill=tk.BOTH, expand=True)
        ttk.Label(quadro, text=explicacao, wraplength=380, justify=tk.LEFT).pack(
            anchor="w", pady=(0, 8))

        meio = ttk.Frame(quadro)
        meio.pack(fill=tk.BOTH, expand=True)
        self.lista = tk.Listbox(meio, height=14, width=40, selectmode=tk.EXTENDED,
                                activestyle="none")
        rolagem = ttk.Scrollbar(meio, orient=tk.VERTICAL, command=self.lista.yview)
        self.lista.configure(yscrollcommand=rolagem.set)
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rolagem.pack(side=tk.LEFT, fill=tk.Y)

        lateral = ttk.Frame(meio, padding=(8, 0, 0, 0))
        lateral.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Button(lateral, text="Remover", command=self.remover).pack(fill=tk.X)
        if not ordenar:
            ttk.Button(lateral, text="▲ Subir", command=lambda: self.mover(-1)).pack(
                fill=tk.X, pady=(12, 0))
            ttk.Button(lateral, text="▼ Descer", command=lambda: self.mover(1)).pack(
                fill=tk.X, pady=(4, 0))
        ttk.Button(lateral, text="Restaurar padrão", command=self.restaurar).pack(
            fill=tk.X, side=tk.BOTTOM)

        nova = ttk.Frame(quadro)
        nova.pack(fill=tk.X, pady=(8, 0))
        self.var_novo = tk.StringVar()
        campo = ttk.Entry(nova, textvariable=self.var_novo)
        campo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        campo.bind("<Return>", lambda _: self.adicionar())
        ttk.Button(nova, text="Adicionar", command=self.adicionar).pack(side=tk.LEFT, padx=(6, 0))

        rodape = ttk.Frame(quadro)
        rodape.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(rodape, text="Salvar", command=self.salvar).pack(side=tk.RIGHT, padx=6)

        self._preencher(itens)
        self.bind("<Delete>", lambda _: self.remover())
        self.bind("<Escape>", lambda _: self.destroy())
        campo.focus_set()
        self.grab_set()

    def _itens(self) -> list[str]:
        return list(self.lista.get(0, tk.END))

    def _preencher(self, itens):
        if self.ordenar:
            itens = sorted(itens, key=str.casefold)
        self.lista.delete(0, tk.END)
        for item in itens:
            self.lista.insert(tk.END, item)

    def adicionar(self):
        novo = " ".join(self.var_novo.get().split())
        if not novo:
            return
        if novo.casefold() in (i.casefold() for i in self._itens()):
            messagebox.showinfo("Já existe", f"“{novo}” já está na lista.", parent=self)
            return
        itens = self._itens()
        # Item novo entra antes da categoria de reserva, que fica sempre no fim.
        fim = next((i for i, item in enumerate(itens) if item.casefold() in self.fixos),
                   len(itens))
        self._preencher(itens[:fim] + [novo] + itens[fim:])
        self.var_novo.set("")
        posicao = self._itens().index(novo)
        self.lista.see(posicao)
        self.lista.selection_clear(0, tk.END)
        self.lista.selection_set(posicao)

    def remover(self):
        selecionados = self.lista.curselection()
        travados = [self.lista.get(i) for i in selecionados
                    if self.lista.get(i).casefold() in self.fixos]
        if travados:
            messagebox.showinfo("Não dá para remover",
                                f"“{travados[0]}” é a categoria de reserva, usada quando "
                                "nenhuma outra serve. Ela sempre existe.", parent=self)
        for i in reversed(selecionados):
            if self.lista.get(i).casefold() not in self.fixos:
                self.lista.delete(i)

    def mover(self, passo):
        selecionados = list(self.lista.curselection())
        if len(selecionados) != 1:
            return
        i = selecionados[0]
        j = i + passo
        if not 0 <= j < self.lista.size():
            return
        item = self.lista.get(i)
        self.lista.delete(i)
        self.lista.insert(j, item)
        self.lista.selection_set(j)
        self.lista.see(j)

    def restaurar(self):
        if messagebox.askyesno("Restaurar padrão",
                               "Voltar para a lista que vem com o programa?", parent=self):
            self._preencher(self.padrao)

    def salvar(self):
        itens = self._itens()
        if not itens:
            messagebox.showwarning("Lista vazia", "Deixe pelo menos um item.", parent=self)
            return
        self.ao_salvar(itens)
        self.destroy()


class JanelaChave(tk.Toplevel):
    """
    Troca a chave da API. Antes de gravar, testa a chave listando os modelos
    (isso não gasta cota). A chave nunca vai para o log.
    """

    def __init__(self, pai, chave_atual, ao_salvar):
        super().__init__(pai)
        self.title("Chave da API do Gemini")
        self.transient(pai)
        self.resizable(False, False)
        self.ao_salvar = ao_salvar

        quadro = ttk.Frame(self, padding=12)
        quadro.pack(fill=tk.BOTH, expand=True)
        ttk.Label(quadro, text=f"Chave atual: {config.chave_mascarada(chave_atual)}").pack(
            anchor="w")
        ttk.Label(quadro, text="Crie uma chave em https://aistudio.google.com/apikey e cole "
                               "abaixo. Ela fica gravada em config\\.env, na pasta do programa.",
                  wraplength=420, justify=tk.LEFT).pack(anchor="w", pady=(6, 8))

        self.var_chave = tk.StringVar()
        self.campo = ttk.Entry(quadro, textvariable=self.var_chave, show="•", width=56)
        self.campo.pack(fill=tk.X)
        self.campo.bind("<Return>", lambda _: self.testar_e_salvar())
        self.var_mostrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(quadro, text="Mostrar o que estou digitando", variable=self.var_mostrar,
                        command=lambda: self.campo.configure(
                            show="" if self.var_mostrar.get() else "•")).pack(anchor="w",
                                                                               pady=(4, 0))

        if os.environ.get("GEMINI_API_KEY"):
            ttk.Label(quadro, foreground="#a15c00", wraplength=420, justify=tk.LEFT,
                      text="Atenção: existe uma variável GEMINI_API_KEY nas configurações do "
                           "Windows, e ela vence o config\\.env. Apague essa variável para a chave "
                           "salva aqui valer.").pack(anchor="w", pady=(8, 0))

        self.var_situacao = tk.StringVar()
        ttk.Label(quadro, textvariable=self.var_situacao, wraplength=420,
                  justify=tk.LEFT).pack(anchor="w", pady=(8, 0))

        rodape = ttk.Frame(quadro)
        rodape.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        self.botao = ttk.Button(rodape, text="Testar e salvar", command=self.testar_e_salvar)
        self.botao.pack(side=tk.RIGHT, padx=6)

        self.bind("<Escape>", lambda _: self.destroy())
        self.campo.focus_set()
        self.grab_set()

    def testar_e_salvar(self):
        chave = self.var_chave.get().strip()
        if not chave:
            return
        self.botao.configure(state=tk.DISABLED)
        self.var_situacao.set("Testando a chave…")
        resultado = {}

        def testar():
            # Fora da thread da janela, para ela não congelar se a rede demorar.
            try:
                cliente = genai.Client(api_key=chave)
                resultado["modelos"] = sum(1 for _ in cliente.models.list())
            except Exception as erro:
                resultado["erro"] = erro

        tarefa = threading.Thread(target=testar, daemon=True)
        tarefa.start()
        self._esperar(tarefa, chave, resultado)

    def _esperar(self, tarefa, chave, resultado):
        if tarefa.is_alive():
            self.after(150, self._esperar, tarefa, chave, resultado)
            return
        if not self.winfo_exists():
            return
        self.botao.configure(state=tk.NORMAL)
        if "erro" in resultado:
            from gemini_client import descrever_erro
            self.var_situacao.set(f"✖ A chave não funcionou: {descrever_erro(resultado['erro'])}")
            if messagebox.askyesno("Chave não testada",
                                   "O teste falhou. Se o problema for a internet, a chave pode "
                                   "estar certa.\n\nSalvar mesmo assim?", parent=self):
                self._gravar(chave)
            return
        self._gravar(chave)

    def _gravar(self, chave):
        self.ao_salvar(chave)
        self.destroy()


class JanelaPython(tk.Toplevel):
    """
    Escolhe o Python que o Iniciar.bat vai usar: automático, um dos encontrados
    no computador, ou um python.exe qualquer. Testa antes de gravar.
    """

    AUTOMATICO = "Automático (recomendado)"

    def __init__(self, pai, escolhido_atual, ao_salvar):
        super().__init__(pai)
        self.title("Python do programa")
        self.transient(pai)
        self.resizable(False, False)
        self.ao_salvar = ao_salvar

        quadro = ttk.Frame(self, padding=12)
        quadro.pack(fill=tk.BOTH, expand=True)
        ttk.Label(quadro, text=f"Em uso agora: {pythons.em_uso()}", wraplength=480,
                  justify=tk.LEFT).pack(anchor="w")
        ttk.Label(quadro, wraplength=480, justify=tk.LEFT, text=(
            "Automático usa o Python portátil (.python_embed), se existir; senão, o "
            "instalado no computador. A troca vale quando o programa abre de novo. "
            "Se faltar alguma biblioteca no Python escolhido, o Iniciar.bat instala "
            "na primeira vez (precisa de internet).")).pack(anchor="w", pady=(6, 10))

        self.encontrados = pythons.candidatos()
        opcoes = [self.AUTOMATICO] + [self._rotulo(p) for p in self.encontrados]
        self.var_escolha = tk.StringVar(value=escolhido_atual or self.AUTOMATICO)
        linha = ttk.Frame(quadro)
        linha.pack(fill=tk.X)
        ttk.Combobox(linha, textvariable=self.var_escolha, values=opcoes, width=62).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(linha, text="Procurar…", command=self.procurar).pack(side=tk.LEFT, padx=(6, 0))

        self.var_situacao = tk.StringVar()
        ttk.Label(quadro, textvariable=self.var_situacao, wraplength=480,
                  justify=tk.LEFT).pack(anchor="w", pady=(8, 0))

        rodape = ttk.Frame(quadro)
        rodape.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        self.botao = ttk.Button(rodape, text="Testar e salvar", command=self.testar_e_salvar)
        self.botao.pack(side=tk.RIGHT, padx=6)

        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()

    @staticmethod
    def _rotulo(exe: Path) -> str:
        return f"{exe}   (portátil)" if exe == pythons.PORTATIL else str(exe)

    def _caminho_escolhido(self) -> str:
        texto = self.var_escolha.get().strip()
        if texto in ("", self.AUTOMATICO):
            return ""
        return texto.removesuffix("(portátil)").strip().strip('"')

    def procurar(self):
        arquivo = filedialog.askopenfilename(
            parent=self, title="Escolha o python.exe",
            filetypes=[("Python", "python.exe"), ("Programas", "*.exe")])
        if arquivo:
            self.var_escolha.set(str(Path(arquivo)))

    def testar_e_salvar(self):
        caminho = self._caminho_escolhido()
        alvo = Path(caminho) if caminho else (
            pythons.PORTATIL if pythons.PORTATIL.exists() else None)
        if alvo is None:
            self.ao_salvar("")   # automático sem portátil: o Iniciar.bat procura sozinho
            self.destroy()
            return
        self.botao.configure(state=tk.DISABLED)
        self.var_situacao.set("Testando…")
        resultado = {}
        tarefa = threading.Thread(target=lambda: resultado.update(t=pythons.testar(alvo)),
                                  daemon=True)
        tarefa.start()
        self._esperar(tarefa, caminho, resultado)

    def _esperar(self, tarefa, caminho, resultado):
        if tarefa.is_alive():
            self.after(150, self._esperar, tarefa, caminho, resultado)
            return
        if not self.winfo_exists():
            return
        self.botao.configure(state=tk.NORMAL)
        teste = resultado["t"]
        if not teste.ok:
            self.var_situacao.set(f"✖ Não serve: {teste.erro}")
            return
        faltando = (f" Faltam bibliotecas ({', '.join(teste.faltando)}); o Iniciar.bat "
                    "instala na próxima abertura." if teste.faltando else "")
        self.var_situacao.set(f"✔ Python {teste.versao} funciona.{faltando}")
        self.ao_salvar(caminho)
        self.destroy()
