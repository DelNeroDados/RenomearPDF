# Por que o RenomearPDF é assim

Este documento explica o raciocínio por trás do projeto: por que o código está
dividido desse jeito, por que cada biblioteca foi escolhida, por que as funções
estão na ordem em que estão e o que foi deixado de fora de propósito.

Ele não é um manual de uso (esse é o [README.md](README.md)). É a conversa que
eu teria com alguém que vai mexer no código e quer entender **por que** as
coisas são como são, antes de mudar alguma delas.

---

## Sumário

1. [O ponto de partida](#1-o-ponto-de-partida)
2. [Quatro promessas que guiam todo o resto](#2-quatro-promessas-que-guiam-todo-o-resto)
3. [Arquitetura: quem conversa com quem](#3-arquitetura-quem-conversa-com-quem)
4. [O caminho de um PDF, do início ao fim](#4-o-caminho-de-um-pdf-do-início-ao-fim)
5. [Escolha de ferramentas e bibliotecas](#5-escolha-de-ferramentas-e-bibliotecas)
6. [Como usamos o Gemini](#6-como-usamos-o-gemini)
7. [Threads, fila e o botão Cancelar](#7-threads-fila-e-o-botão-cancelar)
8. [O cache](#8-o-cache)
9. [Nomes de arquivo](#9-nomes-de-arquivo)
10. [A cópia final](#10-a-cópia-final)
11. [Configuração](#11-configuração)
12. [Ordem das funções dentro dos arquivos](#12-ordem-das-funções-dentro-dos-arquivos)
13. [Testes](#13-testes)
14. [Segurança e privacidade](#14-segurança-e-privacidade)
15. [O que ficou de fora, e por quê](#15-o-que-ficou-de-fora-e-por-quê)

---

## 1. O ponto de partida

A primeira versão do programa era um único arquivo de 330 linhas. Ela funcionava,
mas tinha problemas que só aparecem com o uso:

- **Podia travar para sempre.** O laço de novas tentativas nunca contava as
  tentativas. Bastava o Gemini devolver um erro qualquer para o programa ficar
  girando sem parar.
- **A janela congelava.** Tudo rodava na mesma thread da interface, com uma pausa
  fixa de 5 segundos depois de cada PDF. Com 18 arquivos eram uns 2 minutos de
  janela "Não respondendo".
- **Gastava cota antes de começar.** Para descobrir qual modelo usar, fazia uma
  chamada de teste em cada modelo até um responder.
- **Estragava títulos.** O `str.capitalize()` do Python rebaixa todas as letras
  menos a primeira: "Teoria de Einstein sobre o DNA" virava "Teoria de einstein
  sobre o dna".
- **Podia apagar arquivos.** Dois PDFs com o mesmo nome novo: o segundo
  sobrescrevia o primeiro sem aviso.
- **Não lia PDF escaneado.** Mandava ao Gemini só o texto extraído e, num PDF que
  é foto de página, não há texto nenhum para extrair.
- **Usava pouco a IA.** Pedia três campos, num JSON descrito em texto livre, e
  depois tentava limpar a resposta com `replace("```json", "")`.

Cada decisão descrita abaixo responde a um ou mais desses problemas.

---

## 2. Quatro promessas que guiam todo o resto

Quando duas soluções pareciam igualmente boas, o desempate foi sempre uma destas
quatro promessas, nesta ordem de prioridade:

1. **Os originais são sagrados.** O programa nunca move, renomeia, sobrescreve ou
   apaga um arquivo que já existia. Ele só lê e copia.
2. **A janela nunca congela.** Qualquer coisa que leve mais de um instante roda
   em segundo plano.
3. **Cada chamada à IA é cara.** Cota gratuita acaba, cota paga custa dinheiro.
   Nada é enviado duas vezes sem necessidade.
4. **A IA sugere, a pessoa decide.** O resultado aparece numa tabela editável.
   Nada é copiado sem revisão e confirmação.

---

## 3. Arquitetura: quem conversa com quem

```text
                     Renomeador.py   (só liga o programa)
                           │
                           ▼
                        gui.py       (a janela)
                      ╱    │    ╲
                     ▼     ▼     ▼
          pipeline.py  naming.py  organizer.py
           ╱    │    ╲               │
          ▼     ▼     ▼              ▼
   gemini_   pdf_    cache.py     naming.py
   client.py tools.py
       │                │
       ▼                ▼
   schema.py ◄──────────┘          config.py (lido pela gui)
```

### Por que separar em vários arquivos

Cada arquivo responde a **uma pergunta só**:

| Arquivo | Pergunta que ele responde |
|---|---|
| `pdf_tools.py` | O que tem dentro deste PDF? |
| `gemini_client.py` | O que a IA acha deste PDF? |
| `cache.py` | Já analisei este PDF antes? |
| `schema.py` | Que formato tem a resposta? |
| `naming.py` | Como deve se chamar o arquivo? |
| `organizer.py` | Como copio sem estragar nada? |
| `pipeline.py` | Como analiso vários ao mesmo tempo sem travar a janela? |
| `gui.py` | O que a pessoa vê e clica? |
| `config.py` | Quais são as configurações? |

A vantagem é prática. Se amanhã o Google mudar a API, só o `gemini_client.py`
muda. Se alguém quiser uma interface web no lugar do Tkinter, troca o `gui.py`
e reaproveita o resto inteiro. E dá para testar as regras de nome sem abrir
janela nem gastar cota.

### Por que as setas só descem

Os módulos de baixo não sabem que os de cima existem. O `gemini_client.py` não
importa nada da interface; o `naming.py` não sabe que existe um Gemini. Isso
evita importações circulares e deixa claro onde cada mudança deve acontecer.

Há um único ponto em que um módulo de baixo "fala" com um de cima: o
`ClienteGemini` tem um atributo `ao_aviso`, uma função que ele chama quando quer
avisar algo ("trocando de modelo"). Quem está em cima troca essa função pela
dele. Assim o cliente avisa sem precisar saber quem está ouvindo.

### Por que não é um pacote instalável

Não há `setup.py` nem `pyproject.toml`, e os arquivos ficam todos na raiz.
O programa é uma ferramenta de mesa, usada por quem baixa a pasta e roda
`python Renomeador.py`. Um pacote instalável adicionaria cerimônia (estrutura
`src/`, instalação em modo editável) sem benefício para esse uso.

---

## 4. O caminho de um PDF, do início ao fim

1. **A pessoa escolhe a pasta e clica em Analisar** (`gui.analisar`).
   O programa lista os PDFs (`pdf_tools.listar_pdfs`) e já desenha a tabela
   inteira, com todas as linhas em ⏳. Ver a lista na hora tranquiliza: mostra
   que o programa entendeu o que tem para fazer.

2. **Uma thread conecta ao Gemini** (`gui._iniciar_rodada`). Ela lista os
   modelos disponíveis, o que valida a chave sem gastar cota, e monta a fila de
   modelos. Isso roda fora da janela porque depende da internet.

3. **O processador distribui os PDFs entre 4 threads** (`pipeline.Processador`).

4. **Para cada PDF** (`pipeline.analisar_um`):
   - calcula o hash do arquivo;
   - **se o hash está no cache, devolve na hora** e pula todo o resto;
   - senão, lê o PDF, pega o texto e recorta as 5 primeiras páginas;
   - espera a sua vez no limitador de taxa;
   - manda o recorte ao Gemini e recebe um `MetadadosPDF`;
   - guarda no cache.

5. **O resultado vai para uma fila** e a thread passa ao próximo PDF.

6. **A janela recolhe a fila a cada 150 ms** (`gui._recolher_eventos`),
   preenche a linha correspondente e calcula o nome novo com o modelo atual.

7. **A pessoa revisa**: edita células, reanalisa linhas com instrução, tira
   linhas da lista.

8. **A pessoa clica em Copiar** (`organizer.copiar`): cada arquivo é copiado
   para `saída/Categoria/Novo nome.pdf`, sem sobrescrever nada, e um log é gravado.

A ordem do passo 4 importa. O cache é consultado **antes** de abrir o PDF
porque calcular um hash é muito mais rápido do que extrair texto e montar um
recorte. Na prática, isso fez uma pasta já analisada abrir em 2 a 4 segundos em
vez de 22.

---

## 5. Escolha de ferramentas e bibliotecas

A regra foi: **usar o mínimo de dependências, e só as que se pagam.** O
programa inteiro depende de duas bibliotecas de fora: `google-genai` e `pypdf`.

### Python

O problema é ler arquivos, chamar uma API e mostrar uma tabela, coisas em que o
Python é forte. A primeira versão já era Python, e quem mantém o projeto já o
conhece. A versão mínima é a 3.10, por causa da sintaxe `str | None` nas
anotações de tipo.

### Tkinter, e não PyQt, CustomTkinter ou web

A pedida foi "o mais leve e fácil de implementar". O Tkinter:

- **já vem com o Python**: zero instalação, zero megabytes a mais;
- tem o `ttk.Treeview`, que é exatamente o componente de tabela de que precisamos;
- com o tema `vista`, parece um programa nativo do Windows.

Alternativas consideradas:

| Opção | Por que não |
|---|---|
| PyQt / PySide | Muito mais bonito e poderoso, mas acrescenta dezenas de megabytes e tem curva de aprendizado. Exagero para uma tabela e meia dúzia de botões. A licença do PyQt (GPL) também complica a distribuição. |
| CustomTkinter | Visual moderno, mas não tem um componente de tabela próprio: acabaríamos usando o `ttk.Treeview` do mesmo jeito. |
| Interface web local (Flask, Streamlit) | Exige servidor rodando e navegador aberto, e escolher uma pasta do computador pelo navegador é desajeitado. |

### `ttk.Treeview`, e não uma grade de widgets

A primeira versão criava um `Label`, um `Combobox` e um `Text` por célula. Com
100 PDFs eram mais de 700 widgets, e o Tkinter fica lento com tantos. O
`Treeview` desenha a tabela inteira como um só componente: rápido com milhares
de linhas, e ainda dá ordenação por coluna e seleção múltipla de graça. A edição
é feita pondo um campo temporário por cima da célula no duplo clique
(`gui.editar_celula`). É o jeito tradicional de editar um `Treeview`.

### `google-genai`, e não `google-generativeai` ou chamadas diretas

O `google-generativeai` é o SDK antigo e foi descontinuado pelo Google. O
`google-genai` é o oficial atual e tem três recursos de que precisamos:

- **saída estruturada**: passamos uma classe Pydantic e o Gemini é obrigado a
  responder naquele formato;
- **envio de arquivos** direto na requisição (`Part.from_bytes`);
- **erros tipados** (`errors.APIError` com `.code`), o que permite decidir com
  segurança o que fazer com cada erro.

Chamar a API REST "na mão" com `httpx` seria possível, mas teríamos de
reimplementar tudo isso.

### `pypdf`, e não PyMuPDF ou pdfplumber

| Opção | Por que não |
|---|---|
| **PyMuPDF** | Mais rápido e extrai texto melhor, mas tem licença **AGPL** (obriga a abrir o código de qualquer coisa que o use) e traz binários nativos grandes. |
| **pdfplumber** | Excelente para tabelas, mas é mais lento e traz mais dependências. Não precisamos de tabelas. |

O `pypdf` é Python puro, tem licença BSD e faz bem as três coisas de que
precisamos: ler metadados, extrair texto e **montar um PDF novo só com algumas
páginas**. Essa última é o que viabiliza enviar o recorte ao Gemini.

E a qualidade do texto extraído pesa pouco aqui: quem lê o PDF de verdade é o
Gemini. O texto do `pypdf` só é usado como plano B.

### Pydantic

Vem junto com o `google-genai`, então não é dependência extra. Serve para duas
coisas ao mesmo tempo: descreve para o Gemini o formato da resposta e valida a
resposta que chega. As descrições dos campos (`Field(description=...)`) viram
instruções para a IA: é por elas que o Gemini sabe, por exemplo, que numa tese
o autor é o aluno, não o orientador.

### SQLite para o cache, e não um arquivo JSON

O SQLite vem com o Python. Comparado a um JSON:

- grava um registro de cada vez, sem reescrever o arquivo inteiro a cada PDF;
- não corrompe o arquivo se o programa fechar no meio de uma gravação;
- aguenta milhares de registros sem ficar lento.

### Threads, e não `asyncio` ou processos

O trabalho é quase todo **espera**: esperar a rede, esperar a cota. Para esse
tipo de trabalho, threads resolvem bem, e o `ThreadPoolExecutor` da biblioteca
padrão já faz o pool.

- `asyncio` exigiria reescrever a interface, porque o Tkinter não conversa
  naturalmente com ele.
- Processos (`multiprocessing`) servem para cálculo pesado, que não é o caso,
  e complicariam o compartilhamento do cache e do limitador de taxa.

### Sem `python-dotenv`

Ler um `.env` com linhas `CHAVE=valor` são 10 linhas de código (`config._ler_env`).
Uma dependência a menos para instalar e manter.

### `Iniciar.bat`

O público do programa é quem organiza artigos, não necessariamente quem programa.
Pedir para abrir um terminal, instalar dependências e criar um `.env` à mão é
onde a maioria das pessoas desiste. O `.bat` faz isso tudo com dois cliques:

- **procura o Python em três lugares**, nesta ordem: o Python portátil da pasta
  de cima (o jeito como o projeto nasceu), o lançador `py` (que vem com o
  instalador oficial) e o `python` do PATH;
- **testa o Python de verdade**, em vez de só ver se o comando existe. O Windows
  traz um `python.exe` falso que só abre a Microsoft Store, e sem esse teste o
  `.bat` acharia que está tudo certo;
- **instala as bibliotecas só se faltarem**, então da segunda vez em diante ele
  abre direto;
- **cria o `.env` e abre o Bloco de Notas** na primeira vez, e avisa se a chave
  ainda é a de exemplo;
- **só pausa se der erro**: quando o programa fecha normalmente, a janela preta
  some sozinha.

A opção `--testar` faz todas as verificações sem abrir o programa. Ela existe
para conferir uma instalação nova sem ficar com uma janela aberta.

Foi escolhido um `.bat`, e não um executável empacotado (PyInstaller), porque
dá para ler o que ele faz antes de rodar, não dispara alerta de antivírus e não
precisa ser refeito a cada mudança no código. O arquivo `.gitattributes` garante
que ele continue com as quebras de linha do Windows depois de baixado do GitHub;
com quebras de linha de Linux, o `cmd.exe` se perde.

### `pytest`

É o padrão de fato para testes em Python, e permite escrever testes como
funções simples, com `assert` comum. A pasta temporária (`tmp_path`) e a troca
de funções (`monkeypatch`) que ele oferece são exatamente o que os testes daqui
precisam.

---

## 6. Como usamos o Gemini

### Enviamos o PDF, não só o texto

O Gemini lê PDF diretamente, inclusive páginas escaneadas, e enxerga o layout:
sabe que o texto grande no topo da capa é o título e que o nome embaixo é o
autor. Mandar só o texto extraído joga essa informação fora. O teste com a pasta
real mostrou a diferença: o `vol17a35.pdf`, que não tem uma letra de texto
extraível, foi identificado corretamente.

Se o Gemini recusar o PDF (erro 400, normalmente arquivo malformado), o
programa reenvia só o texto (`ClienteGemini.analisar`).

### Só as primeiras 5 páginas

Capa, folha de rosto, ficha catalográfica e resumo estão sempre no começo.
Mandar uma tese de 250 páginas gastaria dezenas de vezes mais tokens sem
melhorar nada. O número é configurável (`PDF_PAGINAS`) para os casos raros em
que a informação aparece depois.

Se mesmo o recorte passar de 15 MB (páginas escaneadas em altíssima resolução),
vai só o texto. O limite do Gemini para envio direto é de uns 20 MB, e os 5 MB
de folga evitam surpresas.

### Saída estruturada

Em vez de pedir "me devolva um JSON assim" no texto e torcer, passamos a classe
`MetadadosPDF` em `response_schema`. O Gemini é forçado a responder exatamente
naquele formato, com os tipos certos (ano é número, autores é lista) e a
categoria escolhida de uma lista fechada. Acabou o código frágil de limpeza de
resposta.

### Pedimos mais campos do que o nome usa

O nome do arquivo usa só área, sobrenome, ano e título. Mesmo assim pedimos
autores completos, instituição, periódico, DOI, palavras-chave e um resumo. Eles
quase não custam tokens a mais (a IA já leu as páginas) e aparecem no painel
lateral, ajudando a pessoa a conferir se a IA entendeu o documento certo.

### O campo `confianca`

Pedimos que a IA diga, de 0 a 1, quão segura está. Abaixo de 0,6 a linha fica
amarela. Isso direciona a revisão: em vez de conferir 100 linhas, a pessoa olha
as 5 amarelas. Não é uma medida perfeita, mas na prática a IA marca baixa
confiança justamente nos casos ambíguos: slides sem autor, apostilas sem data.

### Instruções de sistema e temperatura

As regras gerais ("não invente", "orientador não é autor", "metadados embutidos
costumam estar errados") vão em `system_instruction`, separadas dos dados de cada
PDF. A temperatura é 0,1: catalogar é tarefa de precisão, não de criatividade, e
queremos que o mesmo PDF dê o mesmo resultado.

### Metadados e nome do arquivo entram como pistas

Os metadados embutidos (título e autor no próprio PDF) e o nome do arquivo são
enviados, mas marcados explicitamente como "só pistas". Eles costumam estar
errados: é comum o título embutido ser "Microsoft Word - versao_final3.docx".
Mesmo assim, às vezes ajudam a desempatar.

### Reanalisar com instrução

Quando a IA erra, a pessoa pode reenviar com uma correção em texto livre
("o autor é João Pereira"). A instrução entra marcada como "CORREÇÃO DO USUÁRIO
(tem prioridade)". Corrigir uma linha assim costuma ser mais rápido do que
editar quatro campos à mão, e o resultado corrigido vai para o cache.

### Escolha automática do modelo

Os modelos do Gemini mudam o tempo todo. Durante o desenvolvimento, o
`gemini-2.5-flash`, que era a escolha óbvia, foi desativado (passou a dar 404).
Fixar um nome no código é pedir para quebrar.

Por isso, ao conectar, o programa **lista** os modelos da chave (o que não gasta
cota) e monta uma fila (`gemini_client.ordenar_flash`):

1. o modelo fixado no `.env`, se houver;
2. o último que funcionou (anotado em `.cache/ultimo_modelo.txt`);
3. os Flash estáveis, do mais novo para o mais velho;
4. o apelido `gemini-flash-latest`;
5. as versões `lite`, por último.

A família Flash foi escolhida por ser rápida e barata, e porque extrair
metadados de uma capa não exige o raciocínio de um modelo Pro. Previews e
modelos de imagem e voz ficam de fora: os primeiros mudam sem aviso e os outros
não servem para a tarefa.

Lembrar o último modelo que funcionou resolve um problema real: na chave
gratuita, o modelo mais novo esgota a cota diária cedo, e sem a memória cada
nova sessão gastaria tempo batendo nele primeiro.

### O que fazer com cada erro

Esta é a parte mais delicada (`gemini_client._decidir`). Cada erro recebe uma de
três respostas: esperar e tentar de novo, trocar de modelo ou desistir.

| Erro | O que significa | O que fazemos | Por quê |
|---|---|---|---|
| 404 | Modelo desativado | Troca na hora | Não vai voltar |
| 429 com espera longa ou limite **diário** | Cota do dia acabou | Troca na hora | O Google chegou a pedir 18 horas de espera |
| 429 curto | Limite por minuto | Espera o tempo pedido (até 30s) | Passa logo |
| 503 | Modelo sobrecarregado | Tenta mais uma vez; na segunda falha, troca | Às vezes é um pico rápido, às vezes dura horas |
| Timeout ou queda de conexão | Rede | Igual ao 503 | Idem |
| 401, 403, 400 | Chave errada, pedido inválido | Desiste | Insistir não resolve |

Quando um modelo é trocado, **a troca vale para todas as threads**
(`ClienteGemini._trocar_modelo`): não faz sentido cada uma descobrir sozinha que
o modelo está sem cota. E quando chega um 429, o limitador empurra a fila
inteira para frente, não só a thread que levou o erro.

Há um teto de 8 tentativas por PDF, somando todos os modelos, e um timeout de
2 minutos por chamada. São as duas garantias de que nada fica preso para sempre,
que era o defeito mais grave da primeira versão.

### O limitador de taxa

`LimitadorTaxa` funciona como senha de padaria: cada chamada pega o próximo
horário livre e espera até ele chegar. Com 10 requisições por minuto, os horários
ficam a 6 segundos um do outro, não importa quantas threads estejam pedindo. É
mais simples que um "balde de fichas" e suficiente para a necessidade.

O padrão de 10 por minuto é conservador de propósito: funciona na chave gratuita.
Quem tem faturamento ativo sobe no `.env`.

---

## 7. Threads, fila e o botão Cancelar

### A regra do Tkinter

O Tkinter só pode ser mexido pela thread que criou a janela. Se outra thread
alterar um widget, o programa pode travar ou quebrar de formas aleatórias.
Durante o desenvolvimento isso apareceu de verdade, como um
`RuntimeError: main thread is not in main loop`.

### A solução: uma fila de recados

As threads de fundo **nunca** tocam na janela. Elas põem recados numa `Queue`
(`App.eventos`), e a própria janela, a cada 150 ms, recolhe o que chegou
(`gui._recolher_eventos`). É o único ponto do código em que o que acontece em
segundo plano chega à tela, e isso facilita muito entender e depurar.

Cada recado tem a forma `(rodada, tipo, carga)`. O tipo pode ser `resultado`,
`aviso`, `fim` ou `falha_inicio`.

### Por que 150 ms

É rápido o bastante para parecer instantâneo para quem olha e lento o bastante
para não gastar processador à toa.

### O número da rodada

Cada clique em Analisar ou Reanalisar abre uma rodada nova, com um número novo
(`App.geracao`). Isso resolve um problema sutil do Cancelar.

Uma chamada HTTP que já saiu **não tem como ser interrompida** no meio. Na
primeira versão do Cancelar, o botão esperava essas chamadas terminarem, o que
podia levar minutos com a janela bloqueada. Agora o Cancelar:

1. avisa as threads para não começarem nenhum PDF novo;
2. aumenta o número da rodada;
3. marca as linhas pendentes como ⏹ e libera os botões **na hora**.

As chamadas que estavam no ar terminam sozinhas em segundo plano. Quando os
recados delas chegam:

- **avisos e "fim"** da rodada velha são ignorados, porque o número não bate;
- **resultados são aproveitados** mesmo assim: a análise já foi paga, e jogar
  fora seria desperdício. Eles só não mexem na barra de progresso da rodada nova.

### Threads `daemon`

Todas as threads de fundo são `daemon=True`: se a pessoa fechar a janela, elas
morrem junto, e o programa não fica rodando escondido.

---

## 8. O cache

### Chave pelo conteúdo, não pelo nome

O cache usa o SHA-256 do arquivo como chave. Assim, um PDF renomeado, movido ou
copiado para outra pasta continua sendo reconhecido. E dois arquivos com o mesmo
nome e conteúdos diferentes não se confundem.

### Quando o cache é ignorado

- **Reanalisar**: a pessoa pediu explicitamente uma nova análise.
- **Reanalisar com instrução**: o resultado precisa refletir a correção.

Em ambos os casos, o resultado novo substitui o antigo.

### Mudanças de formato

Se uma versão futura acrescentar campos ao `MetadadosPDF`, registros antigos
podem não encaixar. O `Cache.obter` trata isso devolvendo "não encontrado", e o
PDF é simplesmente reanalisado. Não há migração para manter.

---

## 9. Nomes de arquivo

### Modelo configurável

Cada pessoa organiza a biblioteca do seu jeito: por área, por autor, por ano.
Em vez de escolher um formato por todo mundo, o nome é um modelo com campos
(`{area}-{sobrenome}-{ano}-{titulo}`) que pode ser mudado na tela, e a tabela
inteira se atualiza na hora.

### Campos vazios somem com o separador

Sem o ano, o resultado é `Física-Souza-Título.pdf`, e não
`Física-Souza--Título.pdf`. Parece detalhe, mas sem isso metade dos nomes
ficaria feia.

### As regras do Windows

O `naming.finalizar_nome` cuida de tudo que o Windows rejeita ou trata mal:

- caracteres proibidos (`< > : " / \ | ? *`) viram espaço;
- nomes reservados de dispositivos (`CON`, `NUL`, `COM1`...) ganham `_` na frente;
  um arquivo chamado `CON.pdf` simplesmente não pode existir no Windows;
- ponto ou espaço no final são removidos (o Windows os descarta e causa confusão);
- o limite é de 150 caracteres, deixando folga dentro dos 260 que o Windows
  permite para o caminho inteiro.

### Maiúsculas

O título vem da IA já com maiúsculas corretas (pedimos isso no `schema.py`). O
programa só garante que a primeira letra é maiúscula, sem rebaixar o resto: é
isso que preserva siglas e nomes próprios, ao contrário do `capitalize()` da
primeira versão.

### Unicode

Os textos são normalizados para a forma NFC. Sem isso, "é" pode estar guardado
como um caractere só ou como "e" + acento. Os dois parecem iguais na tela, mas
são nomes de arquivo diferentes.

### Nome digitado à mão vira lei

Se a pessoa edita o "Novo nome" diretamente, a linha é marcada como manual, e
mudanças no modelo de nome não mexem mais nela. Seria frustrante perder uma
correção feita à mão por mexer num campo do topo da tela.

### Funções puras

Quase tudo no `naming.py` recebe texto e devolve texto, sem tocar em disco nem
em rede. É onde aparecem mais casos estranhos, e funções puras são as mais
fáceis de testar.

---

## 10. A cópia final

### Copiar, nunca mover

Foi um pedido explícito, e também a decisão mais segura. Se algo der errado, o
pior que acontece é sobrar uma cópia a mais; os originais continuam onde estavam.

### Nunca sobrescrever

`naming.caminho_livre` procura um nome livre (`nome (2).pdf`, `nome (3).pdf`...).
Ele lembra os nomes escolhidos na mesma leva, para dois arquivos novos com o
mesmo nome também não se atropelarem, e compara ignorando maiúsculas, porque o
Windows também ignora.

### Subpastas por categoria

Artigos, Teses, Dissertações... A categoria vem de uma lista fechada no
`schema.py`, então os nomes das pastas são sempre os mesmos, sem "Tese",
"Teses" e "tese de doutorado" espalhados.

### `shutil.copy2`

Preserva a data de modificação original. Para quem organiza por data, a cópia
continua dizendo quando o documento foi realmente salvo.

### Um erro não para os outros

Se um arquivo falhar (disco cheio, permissão), os demais são copiados
normalmente, e o erro aparece no resumo final.

### O log

Cada cópia grava `_logs/copia_AAAAMMDD_HHMMSS.json`, com origem e destino de cada
arquivo. Se a pessoa estranhar alguma coisa depois, dá para rastrear de onde
veio cada cópia.

### Linhas puladas

Linhas com erro, pendentes ou canceladas não são copiadas, porque não há um nome
confiável para elas. A exceção é quando a pessoa digitou um nome à mão: aí ela
assumiu a responsabilidade. O aviso de confirmação diz quantas serão puladas e
por quê.

---

## 11. Configuração

- **Arquivo `.env`**: é o formato mais conhecido para guardar segredos fora do
  código, e o `.gitignore` o bloqueia.
- **Variável de ambiente vence o `.env`**: assim dá para trocar a chave
  temporariamente sem editar arquivo nenhum.
- **Tudo tem padrão, menos a chave**: o programa funciona com um `.env` de uma
  linha só.
- **Valores inválidos não quebram nada**: `GEMINI_RPM=abc` vira o padrão (10).
  É melhor funcionar com o padrão do que não abrir por causa de um erro de digitação.
- **O `.env` é relido a cada análise**: mudar o número de páginas ou o limite
  por minuto não exige fechar o programa.

---

## 12. Ordem das funções dentro dos arquivos

O código foi organizado para ser lido **de cima para baixo**, como um texto.

### Do geral para o detalhe

Em cada arquivo, o que é mais importante e mais usado de fora vem primeiro. Os
detalhes de implementação, os auxiliares com `_` no começo, vêm depois. Quem abre
o `gemini_client.py` vê primeiro a classe `ClienteGemini` e o método `analisar`,
que é o que todo mundo usa. Os detalhes de como os erros são classificados ficam
lá embaixo, para quem precisar.

### A janela, na ordem em que é usada

O `gui.py` está dividido em sete seções numeradas, na ordem em que a pessoa usa
o programa:

1. Montagem da janela
2. Escolha das pastas
3. Análise
4. Recebendo os resultados
5. Revisão na tabela
6. Painel lateral
7. Cópia final

Quem quer entender o que acontece quando clica em um botão encontra o código no
lugar em que esperaria encontrar.

### O caminho de um PDF, na ordem do caminho

O `pipeline.analisar_um` faz o passo a passo inteiro de um PDF em sequência
(hash, cache, leitura, Gemini, cache), sem saltos. Dá para ler a função e saber
exatamente o que acontece com um arquivo.

### Comentários explicam o porquê

Os comentários evitam repetir o que o código já diz ("incrementa o contador").
Eles explicam a razão que não está escrita em lugar nenhum: por que o cache é
consultado antes de abrir o PDF, por que 15 MB, por que um 429 às vezes troca de
modelo e às vezes espera.

### Nomes em português

O domínio do programa é em português (tese, dissertação, orientador, ficha
catalográfica), e quem mantém o projeto também. Misturar `get_thesis_advisor`
com "orientador" na conversa só atrapalha. Os nomes das bibliotecas e de
conceitos técnicos consagrados (`cache`, `hash`, `status`) ficam como são.

---

## 13. Testes

### Um Gemini falso

Os testes (`tests/test_fluxo.py`) trocam o cliente de verdade por um falso, que
devolve respostas ou erros predefinidos. Assim os testes:

- rodam sem internet e não gastam cota;
- são **determinísticos**: dá para simular "primeiro um 503, depois um 404,
  depois sucesso" e conferir se o programa trocou de modelo como deveria. Com a
  API real, isso seria impossível de reproduzir.

A espera entre tentativas (`_dormir`) também é substituída, para os testes não
levarem minutos.

### O que é testado

- **Regras de nome**: campos vazios, caracteres proibidos, nomes reservados,
  limite de tamanho, colisões.
- **Leitura de PDF**: recorte de páginas, arquivo corrompido, pasta de saída ignorada.
- **Cache**: a segunda análise não chama a API; Reanalisar chama.
- **Política de erros**: 429 com espera, 429 persistente, cota diária, 503 seguido
  de 404 com troca de modelo, timeout, chave inválida sem insistência.
- **Confiança baixa** marcada como ⚠.
- **Cópia**: não sobrescreve e não toca nos originais.
- **Ordenação dos modelos.**

### O que não é testado automaticamente

A janela. Testar interface gráfica automaticamente é caro e frágil, e a lógica
importante foi tirada da janela justamente para poder ser testada. A janela foi
testada à mão e com roteiros que a abrem, simulam uma análise completa e um
cancelamento, e conferem o estado final.

---

## 14. Segurança e privacidade

- **A chave nunca fica no código.** Ela mora no `.env`, bloqueado pelo
  `.gitignore`. O repositório traz só o `.env.example`, sem chave.
- **Chaves antigas foram tratadas como vazadas.** A primeira versão tinha a chave
  escrita no código. Essas cópias ficaram numa pasta local (`_old_/`), também
  bloqueada, e a recomendação é rotacioná-las.
- **Os PDFs não vão para o repositório.** Eles são pessoais e muitos têm direitos
  autorais de terceiros. O `.gitignore` bloqueia `PDFs/`, `out/` e qualquer `*.pdf`.
- **O cache também não vai**: ele contém títulos, autores e resumos dos seus
  documentos.
- **O que vai para o Google**: só as primeiras páginas de cada PDF, nada além.
  O README avisa que, no nível gratuito, o Google pode usar esse conteúdo para
  melhorar os produtos dele, e que documentos confidenciais pedem cuidado.

---

## 15. O que ficou de fora, e por quê

Algumas ideias foram consideradas e deixadas para depois, porque a pedida foi
manter o programa leve e simples:

| Ideia | Por que ficou de fora |
|---|---|
| **Batch API do Gemini** (metade do preço, processamento assíncrono) | Só compensa com centenas de PDFs de uma vez, e a resposta pode levar horas. Para pastas do tamanho usado hoje, o modo normal é melhor. |
| **Chat com o PDF** no painel lateral | Útil, mas é outra funcionalidade, com outro fluxo. O "Reanalisar com instrução" cobre o caso principal, que é corrigir um erro da IA. |
| **Confirmação pelo DOI** (consultar a Crossref) | Melhoraria a precisão dos artigos, mas acrescenta outro serviço externo e outra fonte de falhas. |
| **Detecção de duplicatas** por semelhança | O cache por hash já detecta cópias idênticas. Versões diferentes do mesmo artigo exigiriam embeddings: complexidade demais para o ganho. |
| **Modo linha de comando** | A estrutura em módulos permite criar um em poucas linhas, chamando o `pipeline` e o `organizer`. Ainda não houve necessidade. |
| **Mover em vez de copiar, e Desfazer** | Decisão explícita: só copiar. Assim não há o que desfazer. |
| **Modelo Pro** | Mais lento e mais caro, e os Flash deram resultados coerentes em todos os documentos de teste. Continua disponível via `GEMINI_MODEL` para quem quiser. |

Se alguma dessas ideias voltar à mesa, a arquitetura já tem um lugar claro para
ela: o chat e a Crossref entrariam ao lado do `gemini_client.py`, a linha de
comando ao lado do `gui.py`, e nenhuma delas exigiria mexer no resto.
