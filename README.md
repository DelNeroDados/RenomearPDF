# RenomearPDF — Manual de uso

Organizador de PDFs acadêmicos (artigos, teses, dissertações, livros, slides…) que usa a
IA **Gemini**, do Google, para ler cada arquivo, descobrir título, autor, ano, área e tipo de
documento, e **copiar** tudo para uma pasta nova, com nomes padronizados e separado por
categoria.

> **Seus arquivos originais nunca são alterados, movidos ou apagados.** O programa só copia.

---

## Sumário

1. [O que o programa faz](#1-o-que-o-programa-faz)
2. [Instalação (primeira vez)](#2-instalação-primeira-vez)
3. [Como abrir o programa](#3-como-abrir-o-programa)
4. [Conhecendo a tela](#4-conhecendo-a-tela)
5. [Passo a passo](#5-passo-a-passo)
6. [Revisando e corrigindo os resultados](#6-revisando-e-corrigindo-os-resultados)
7. [Modelo do nome dos arquivos](#7-modelo-do-nome-dos-arquivos)
8. [Onde os arquivos vão parar](#8-onde-os-arquivos-vão-parar)
9. [Configurações avançadas (.env)](#9-configurações-avançadas-env)
10. [Cache: análises guardadas](#10-cache-análises-guardadas)
11. [Custos, cotas e privacidade](#11-custos-cotas-e-privacidade)
12. [Solução de problemas](#12-solução-de-problemas)
13. [Perguntas frequentes](#13-perguntas-frequentes)
14. [Para desenvolvedores](#14-para-desenvolvedores)

---

## 1. O que o programa faz

Para cada PDF da pasta escolhida:

1. Lê as **primeiras páginas** (capa, folha de rosto, ficha catalográfica, resumo).
2. Envia essas páginas ao Gemini, que devolve:
   título, subtítulo, autores, ano, categoria, área, subárea, idioma, instituição,
   periódico, DOI, palavras-chave, um resumo curto e um **grau de confiança**.
3. Monta um nome novo, por exemplo:
   `Física-Souza-2020-Ensino de física quântica no Brasil.pdf`
4. Mostra tudo numa tabela para você **revisar e corrigir**.
5. Quando você mandar, **copia** os arquivos para a pasta de saída, em subpastas por categoria.

Funciona também com **PDFs escaneados** (imagens sem texto), porque o Gemini lê a página
como imagem.

**E-books (EPUB, MOBI, AZW3, FB2)** são convertidos para PDF antes da análise. Na cópia, vão
os dois com o mesmo nome novo: o PDF e o e-book original.

**Os outros arquivos da pasta** (DOCX, imagens, ZIP…) aparecem na tabela com 📎, não vão
para a IA e são copiados, com o nome original, para `.verificar\Outros formatos`. Assim,
tudo o que está na pasta chega à saída.

---

## 2. Instalação (primeira vez)

### 2.1. Python

É preciso o **Python 3.10 ou mais novo**, com o Tkinter (o instalador oficial de
<https://python.org> já traz). Para conferir:

```powershell
python --version
```

> **Python portátil:** se você usa uma versão portátil (embeddable) em vez da instalada,
> troque `python` pelo caminho completo do `python.exe` em todos os comandos deste manual.

### 2.2. Bibliotecas

Abra o PowerShell **dentro da pasta do projeto** e rode:

```powershell
python -m pip install -r requirements.txt
```

> Entre elas está o **PyMuPDF**, que converte os e-books para PDF.
>
> O pacote certo é o **google-genai** (SDK novo). O antigo `google-generativeai` está
> descontinuado: não instale os dois juntos.

### 2.3. Chave da API do Gemini

1. Acesse <https://aistudio.google.com/apikey> e clique em **Create API key**.
2. Copie a chave.
3. Na pasta `config` do programa, copie o arquivo `.env.example` e renomeie a cópia para `.env`.
4. Abra o `config\.env` no Bloco de Notas e cole a chave:

   ```text
   GEMINI_API_KEY=cole_sua_chave_aqui
   ```

5. Salve.

Depois, para trocar a chave, não precisa mexer no arquivo: use o menu
**Configurações → Chave da API…** (veja a [seção 4](#4-conhecendo-a-tela)).

> O `config\.env` é bloqueado pelo `.gitignore` e **nunca** vai para o GitHub. Não escreva a chave
> em nenhum outro arquivo.

---

## 3. Como abrir o programa

**Jeito mais fácil:** dê dois cliques em **`Iniciar.bat`**. Ele encontra o Python,
instala as bibliotecas que faltarem, cria o `config\.env` (abrindo o Bloco de Notas para você
colar a chave) e abre o programa. Na prática, ele faz sozinho os passos 2.2 e 2.3.

> Para só conferir se está tudo instalado, sem abrir a janela: `Iniciar.bat --testar`.

**Pelo terminal**, dentro da pasta do projeto:

```powershell
python Renomeador.py
```

A janela **"Renomeador de PDFs acadêmicos — Gemini"** se abre.

---

## 4. Conhecendo a tela

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Pasta dos PDFs: [C:\...\Artigos            ] [Escolher…] ☐ Incluir subpastas       │
│                                               [▶ Analisar com IA] [■ Cancelar]      │
│ Pasta de saída: [C:\...\Artigos\out        ] [Escolher…]  Modelo do nome: [......]  │
│ Esforço da IA:  Econômico ──■──── Máximo   Normal: flash, 5 páginas  ☑ Refazer dúvidas │
├──────────────────────────────────────────────────────────┬────────────────────────┤
│  TABELA DE ARQUIVOS                                      │ [📄 Abrir PDF]          │
│  St │ Arquivo │ Categoria │ Área │ Sobrenome │ Ano │ ... │ [Ver texto]             │
│  ✔  │ 0702... │ Artigos   │ Enf. │ Lima      │2019 │ ... │ [↻ Reanalisar…]         │
│  ⚠  │ 2018... │ Teses     │ ...  │ ...       │ ... │ ... │                         │
│  ✖  │ vol1... │ Outros    │      │           │     │ ... │  PAINEL DE DETALHES     │
├──────────────────────────────────────────────────────────┴────────────────────────┤
│ [████████░░░░] Analisando 12/18 com gemini-…              [✔ Copiar e renomear]    │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Menu Configurações

| Opção | Para quê |
|---|---|
| **Categorias…** | Adicionar, remover ou mudar a ordem das categorias. Cada categoria vira uma subpasta na cópia, e a IA é obrigada a escolher uma delas. `Outros` sempre existe, para quando nenhuma serve. |
| **Áreas…** | Adicionar ou remover áreas. Elas são sugestões: a IA prefere uma delas, mas pode responder outra, e na tabela você pode digitar qualquer área. |
| **Chave da API…** | Trocar a chave do Gemini. O programa testa a chave antes de gravar no `config\.env` (o teste não gasta cota), e a análise seguinte já usa a chave nova. |
| **Python…** | Escolher qual Python abre o programa: **Automático** (o portátil `.python_embed`, se existir; senão, o instalado), um dos encontrados no computador, ou um `python.exe` qualquer (**Procurar…**). O programa testa antes de gravar e oferece reiniciar, porque a troca só vale quando ele abre de novo. Se faltarem bibliotecas no Python escolhido, o `Iniciar.bat` instala na abertura seguinte. |
| **Abrir o log** | Abre o `logs\renomearpdf.log`, o registro de tudo o que aconteceu: arquivos analisados, conversões, cancelamentos, cópias e erros. |

As listas ficam em `config\listas.json`. **Restaurar padrão** volta
para as listas originais. A mudança vale para as próximas análises: arquivos que já estão no
cache mantêm o que a IA respondeu antes. Para refazer um deles, use **Reanalisar**.

### Parte de cima

| Elemento | Para quê |
|---|---|
| **Pasta dos PDFs** | Pasta onde estão os arquivos. Pode ser **qualquer pasta do computador**, inclusive pendrive ou rede. |
| **Escolher…** | Abre o seletor de pastas. Você também pode colar o caminho direto no campo. |
| **Incluir subpastas** | Marcado: procura PDFs também dentro das subpastas. Desmarcado: só na pasta escolhida. |
| **▶ Analisar com IA** | Começa a análise. |
| **■ Cancelar** | Para a análise **na hora** e libera a janela. Os arquivos que faltavam ficam com ⏹. Se uma análise que já estava em andamento terminar depois, o resultado aparece na tabela mesmo assim. |
| **Pasta de saída** | Para onde as cópias vão. Se ficar vazia, o programa usa `out` dentro da pasta dos PDFs. |
| **Modelo do nome** | Formato dos nomes novos. Veja a [seção 7](#7-modelo-do-nome-dos-arquivos). |
| **Esforço da IA** | Quanto a IA se esforça (e quanto de cota gasta) em cada PDF. Veja a tabela abaixo. |
| **Refazer dúvidas no nível acima** | Marcado (padrão): o que voltar com erro ou confiança abaixo de 60% é refeito **uma vez** no nível seguinte, e fica o melhor dos dois resultados. |

#### Esforço da IA

| Nível | Modelo preferido | Páginas lidas | Raciocínio | Quando usar |
|---|---|---|---|---|
| Econômico | flash-lite | 3 | mínimo | Pastas grandes, artigos com capa simples. Gasta pouca cota. |
| Normal | flash | 5 | baixo | O dia a dia. |
| Caprichado | flash | 10 | alto | Livros escaneados e antigos, em que o título aparece depois da página 5. |
| Máximo | pro | 15 | alto | Casos difíceis. O `pro` costuma não ter cota no nível gratuito; aí o programa usa o flash. |

Se o modelo preferido estiver sem cota, o programa desce para o próximo (por exemplo, do
flash para o flash-lite). O painel de detalhes mostra qual modelo e qual nível analisaram
cada arquivo.

Uma boa forma de economizar: deixe no **Econômico** com **Refazer dúvidas** marcado. Só os
arquivos difíceis gastam a análise mais cara.

### Tabela (centro)

| Coluna | Conteúdo | Editável? |
|---|---|---|
| (status) | Ícone com o resultado da análise | não |
| Arquivo original | Nome atual do arquivo | não |
| Categoria | Tipo do documento; vira o nome da subpasta na saída | ✔ (lista) |
| Área | Grande área do conhecimento | ✔ (lista ou texto livre) |
| Sobrenome | Sobrenome do primeiro autor | ✔ |
| Ano | Ano de publicação ou defesa | ✔ |
| Título | Título da obra | ✔ |
| Novo nome | Nome final do arquivo copiado | ✔ |
| Conf. | Confiança da IA (0 a 100%) | não |

**Ícones de status:**

| Ícone | Cor da linha | Significado |
|---|---|---|
| ⏳ | cinza | Na fila, esperando análise |
| ✔ | normal | Analisado com sucesso |
| ↺ | texto azul | Analisado antes; veio do [cache](#10-cache-análises-guardadas), sem gastar cota |
| ⚠ | **amarelo** | A IA ficou em dúvida (confiança abaixo de 60%). **Confira esta linha.** Se não editar, a cópia vai para `.verificar`. |
| ✖ | **vermelho** | Erro: arquivo corrompido, protegido por senha ou falha da IA. A cópia vai para `.verificar\Sem análise`, com o nome original. |
| 📎 | cinza | Não é PDF nem e-book. Não vai para a IA; na cópia, vai para `.verificar\Outros formatos` com o nome original. |
| ⏹ | cinza | Não analisado porque você clicou em Cancelar. Clique em **▶ Analisar** de novo (o que já foi feito vem do cache) ou selecione e use **Reanalisar**. |

### Painel direito

| Botão | Para quê |
|---|---|
| **📄 Abrir PDF** | Abre o arquivo selecionado no leitor de PDF do Windows. Para um e-book, abre o PDF convertido. |
| **Ver texto** | Mostra o texto das 3 primeiras páginas (útil para copiar e colar). |
| **↻ Reanalisar com instrução…** | Manda as linhas selecionadas de novo para a IA, com uma dica sua. Veja a [seção 6.3](#63-reanalisar-com-instrução). |

Ao clicar numa linha, o painel mostra **todos** os dados que a IA encontrou: autores
completos, instituição, periódico, DOI, palavras-chave, resumo e o modelo e o nível que
fizeram a análise. Linhas com erro mostram
a mensagem de erro.

### Parte de baixo

- **Barra de progresso** e texto de status. Durante a análise, o status mostra avisos como
  *"gemini-3.8-flash sem cota; trocando para gemini-3.5-flash"*, para você saber o que está
  acontecendo. Ao terminar, mostra quantas chamadas foram feitas com cada modelo (assim dá
  para ver se boa parte caiu para o flash-lite) e quantos tokens foram gastos.
- **✔ Copiar e renomear**: faz a cópia final.

---

## 5. Passo a passo

### Passo 1: Escolher a pasta

Clique em **Escolher…** ao lado de *Pasta dos PDFs* e selecione a pasta.
A *Pasta de saída* é preenchida sozinha com `…\out`. Troque se quiser outro lugar.

Marque **Incluir subpastas** se os PDFs estiverem espalhados em várias pastas.

> A pasta de saída é ignorada na busca. Se ela ficar dentro da pasta dos PDFs, os arquivos
> já organizados não são analisados de novo.

### Passo 2: Analisar

Clique em **▶ Analisar com IA**.

- A tabela aparece na hora, com todas as linhas em ⏳.
- Cada linha é preenchida assim que o resultado chega (vários PDFs são analisados ao mesmo tempo).
- A janela **não trava**: você já pode ir revisando as linhas prontas.

Tempo aproximado: com o limite padrão de 10 requisições por minuto, 18 PDFs levam cerca de
**2 minutos**. PDFs que já estão no cache aparecem quase na hora.

### Passo 3: Revisar

Veja a [seção 6](#6-revisando-e-corrigindo-os-resultados). Comece pelas linhas **amarelas (⚠)**
e **vermelhas (✖)**.

### Passo 4: Copiar

Clique em **✔ Copiar e renomear** e confirme.

**Todos os arquivos da lista são copiados.** Os que ficaram com dúvida (⚠), erro (✖) ou sem
análise (⏹) vão para a pasta `.verificar` dentro da saída, para você conferir depois. Uma
linha que você editou conta como conferida e vai para a pasta normal.

No final aparece um resumo com o número de arquivos copiados, quantos foram para
`.verificar`, os erros e o caminho do log. O programa oferece abrir a pasta de saída.

---

## 6. Revisando e corrigindo os resultados

### 6.1. Editar uma célula

1. Dê **duplo clique** na célula (Categoria, Área, Sobrenome, Ano, Título ou Novo nome).
2. Digite ou escolha o valor.
3. **Enter** salva. **Esc** cancela. Clicar fora também salva.

Ao editar **Categoria, Área, Sobrenome, Ano ou Título**, o **Novo nome é refeito
automaticamente** a partir do modelo.

Ao editar o **Novo nome** diretamente, ele passa a ser **manual**: o programa não mexe mais
nele, nem quando você muda o modelo do nome. Para voltar ao automático, reanalise a linha.

### 6.2. Outras ações na tabela

| Ação | Como |
|---|---|
| Ordenar | Clique no título da coluna (clique de novo para inverter). Ex.: ordene por **Conf.** para ver as piores primeiro. |
| Selecionar várias linhas | `Ctrl + clique` ou `Shift + clique` |
| Tirar uma linha da cópia | Selecione e aperte **Delete**. O arquivo **não** é apagado; só sai da lista. |
| Ver detalhes | Clique na linha e olhe o painel direito |

### 6.3. Reanalisar com instrução

Quando a IA errar, você pode mandar o arquivo de novo **com uma correção**:

1. Selecione a linha (ou várias).
2. Clique em **↻ Reanalisar com instrução…**
3. Escreva a dica e clique em OK. Exemplos:
   - `o autor é João Pereira, o orientador não conta`
   - `é uma dissertação de mestrado de 2019`
   - `área: Enfermagem`
   - `o título está na página 2, não na capa`
4. Deixe o campo **vazio** para só pedir uma análise nova, sem usar o cache.

A reanálise gasta uma chamada da API e substitui o resultado guardado no cache.

### 6.4. Linhas com erro (✖)

Linhas com erro **também são copiadas**, mas com o nome original e para
`.verificar\Sem análise`, porque não há dados confiáveis para um nome novo. Para que uma
delas vá para a pasta normal:

- **Reanalise** (às vezes o erro foi temporário); ou
- **edite o Novo nome** à mão. A linha passa a ser copiada com esse nome, na categoria
  escolhida (o padrão é `Outros`).

Um e-book que não pôde ser convertido (protegido por DRM, por exemplo) também fica ✖ e vai
para `.verificar\Sem análise`.

---

## 7. Modelo do nome dos arquivos

O campo **Modelo do nome** define o formato. Campos disponíveis:

| Campo | Exemplo |
|---|---|
| `{area}` | `Física` |
| `{sobrenome}` | `Souza` |
| `{ano}` | `2020` |
| `{titulo}` | `Ensino de física quântica no Brasil` |
| `{tipo}` | `Teses` |

Exemplos de modelo:

| Modelo | Resultado |
|---|---|
| `{area}-{sobrenome}-{ano}-{titulo}` (padrão) | `Física-Souza-2020-Ensino de física quântica no Brasil.pdf` |
| `{sobrenome} ({ano}) {titulo}` | `Souza (2020) Ensino de física quântica no Brasil.pdf` |
| `{ano} - {titulo}` | `2020 - Ensino de física quântica no Brasil.pdf` |
| `{tipo} - {area} - {titulo}` | `Teses - Física - Ensino de física quântica no Brasil.pdf` |

Para aplicar, edite o campo e aperte **Enter** (ou clique fora). Todas as linhas são
refeitas, menos as de nome manual.

**Regras aplicadas automaticamente:**
- Campo vazio some junto com o separador: sem ano, sai `Física-Souza-Título.pdf`.
- Caracteres proibidos no Windows (`< > : " / \ | ? *`) viram espaço.
- Nomes reservados do Windows (`CON`, `NUL`, `COM1`…) ganham `_` na frente.
- O nome é limitado a 150 caracteres.
- Siglas e nomes próprios do título são preservados (`DNA`, `Einstein`).

Para mudar o modelo **padrão** (o que aparece ao abrir), configure `MODELO_NOME` no `config\.env`.

---

## 8. Onde os arquivos vão parar

Com a pasta de saída `C:\Artigos\out`, o resultado fica assim:

```
C:\Artigos\out\
├── Artigos\
│   ├── Enfermagem-Lima-2019-Cuidados paliativos na atenção básica.pdf
│   └── Física-Souza-2020-Ensino de física quântica no Brasil.pdf
├── Teses\
│   └── Educação-Medeiros-2011-Formação de professores de ciências.pdf
├── Livros\
│   ├── História-Reinhardt-2005-Alexandre VI.pdf      (convertido do EPUB)
│   └── História-Reinhardt-2005-Alexandre VI.epub     (o original, com o mesmo nome)
├── Dissertações\
├── Slides e Apresentações\
├── .verificar\
│   ├── Livros\
│   │   └── Outros-Documento sem título.pdf     (confiança baixa)
│   ├── Sem análise\
│   │   └── arquivo_que_deu_erro.pdf            (nome original)
│   └── Outros formatos\
│       └── anotacoes.docx                      (não é PDF nem e-book)
└── _logs\
    └── copia_20261116_153012.json
```

**Categorias possíveis (subpastas):**
Artigos · Teses · Dissertações · Monografias e TCCs · Livros · Capítulos ·
Slides e Apresentações · Apostilas e Material Didático · Outros

**Garantias:**
- Os originais ficam onde estavam, intactos.
- **Nada é sobrescrito.** Se já existir um arquivo com o mesmo nome, a cópia vira
  `nome (2).pdf`, `nome (3).pdf` e assim por diante.
- A data de modificação original do arquivo é mantida.
- O arquivo `_logs\copia_AAAAMMDD_HHMMSS.json` registra de onde veio e para onde foi cada
  arquivo, se ele foi para `.verificar`, e os erros, se houver.

---

## 9. Configurações avançadas (.env)

Todas são opcionais, menos a chave. Edite o `config\.env` e **reabra o programa**.

O que é seu fica separado do código, em três pastas dentro do programa:

| Pasta | O que guarda |
|---|---|
| `config\` | `.env` (chave, Python escolhido e as opções abaixo) e `listas.json` (categorias e áreas) |
| `logs\` | `renomearpdf.log`, o registro do que aconteceu |
| `.cache\` | análises já feitas e os PDFs convertidos dos e-books |

Para levar suas configurações para outra cópia do programa, copie a pasta `config`. Versões
antigas guardavam o `.env` e o `listas.json` na raiz; eles são movidos para `config\`
sozinhos na primeira abertura.

```text
GEMINI_API_KEY=sua_chave
GEMINI_MODEL=
GEMINI_RPM=10
GEMINI_WORKERS=4
NIVEL_IA=1
MODELO_NOME={area}-{sobrenome}-{ano}-{titulo}
```

| Chave | Padrão | O que faz | Quando mudar |
|---|---|---|---|
| `GEMINI_API_KEY` | — | Chave da API | Obrigatória |
| `GEMINI_MODEL` | vazio | Modelo do Gemini. Vazio = escolhe sozinho conforme o **Esforço da IA**, do mais novo para o mais velho, pulando os que estão sem cota hoje (veja a [seção 11](#11-custos-cotas-e-privacidade)). Preenchido, ele é sempre o primeiro a ser tentado. | Para fixar um modelo, ex.: `gemini-2.5-flash` ou um modelo `pro` (mais preciso, mais lento e mais caro) |
| `GEMINI_RPM` | `10` | Máximo de requisições por minuto | Suba (ex.: `300`) se o projeto da chave tiver **faturamento ativo** no Google Cloud. Se aparecerem muitos erros de cota, abaixe. |
| `GEMINI_WORKERS` | `4` | PDFs analisados em paralelo | Suba junto com o RPM em pastas grandes |
| `PYTHON` | vazio | Python usado pelo `Iniciar.bat`. Vazio = automático | Para usar outro Python; mais fácil pelo menu **Configurações → Python…** |
| `NIVEL_IA` | `1` | Posição inicial do controle **Esforço da IA**: 0 Econômico, 1 Normal, 2 Caprichado, 3 Máximo | Se você quase sempre usa outro nível |
| `MODELO_NOME` | `{area}-{sobrenome}-{ano}-{titulo}` | Modelo de nome padrão | Ao gosto |

> **Sobre "plano Pro":** a assinatura Google AI Pro (do app Gemini) **não** aumenta os limites
> da API. Em 16/11/2026, a chave deste projeto respondia como **Free Tier**. O que aumenta é ativar o faturamento no projeto do Google Cloud ligado à chave.
> Confira o seu nível em <https://aistudio.google.com> → *Usage & Billing*.

---

## 10. Cache: análises guardadas

Toda análise bem-sucedida fica guardada em `RenomearPDF\.cache\analises.sqlite`.

- O arquivo é reconhecido pelo **conteúdo**, não pelo nome. Um PDF renomeado ou movido
  continua sendo reconhecido.
- Reabrir a mesma pasta **não gasta cota**: as linhas aparecem com ↺.
- **Reanalisar** ignora o cache e grava o resultado novo.
- O cache anota até que nível o arquivo já foi analisado. Uma análise feita no Econômico
  não é reaproveitada se você pedir Caprichado; a contrária é.
- Para apagar o cache inteiro, feche o programa e apague a pasta `.cache`.

---

## 11. Custos, cotas e privacidade

**Custo:** cada PDF consome uma chamada ao Gemini com 3 a 15 páginas, conforme o nível, e
mais uma se a dúvida for refeita no nível acima. O total de tokens
aparece na barra de status ao final. No nível gratuito, o limite diário de chamadas é baixo.
Com faturamento ativo, o custo de um modelo Flash para algumas centenas de PDFs costuma ser
de centavos a poucos reais. Consulte os preços atuais em <https://ai.google.dev/pricing>.

**Troca automática de modelo:** cada modelo do Gemini tem a sua própria cota e às vezes fica
sobrecarregado. Quando o modelo atual falha, o programa passa sozinho para o próximo:

- **cota diária esgotada** ou modelo desativado: troca na hora;
- **sobrecarga (503)** ou demora: tenta mais uma vez e depois troca.

Quando a cota **diária** de um modelo acaba, o programa anota isso em
`.cache\modelos_sem_cota.json` e não tenta mais esse modelo até o dia seguinte, para não gastar
uma chamada à toa. Se todos os modelos falharem, a linha fica ✖. Espere e reanalise só essas linhas.

**Nível gratuito:** chaves sem faturamento têm um limite **diário** baixo por modelo (em
nov/2026, 20 requisições por dia no `gemini-3.8-flash`). Com a troca automática, uma pasta
pequena ainda passa, mas pastas grandes podem esgotar todos os modelos no mesmo dia.

**Privacidade:** as **primeiras páginas** de cada PDF são enviadas ao Google para análise.
No nível gratuito, o Google pode usar esse conteúdo para melhorar os produtos dele. **Não
use o programa com documentos confidenciais** (dados de clientes, documentos pessoais) sem
faturamento ativo e sem conferir os termos de uso.

---

## 12. Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `ModuleNotFoundError: No module named 'google'` ou `'pypdf'` | Bibliotecas não instaladas | Rode o comando da [seção 2.2](#22-bibliotecas) |
| `'python' não é reconhecido` | Python não instalado ou fora do PATH | Instale pelo python.org marcando *Add to PATH*, ou use o caminho completo do `python.exe` |
| Mensagem **"Chave recusada (401)"** ou **"(403)"** | Chave inválida ou revogada | Gere uma chave nova no AI Studio e troque em **Configurações → Chave da API…** |
| Algo deu errado e você não sabe o quê | — | **Configurações → Abrir o log**: o `logs\renomearpdf.log` registra cada etapa e os erros |
| **"GEMINI_API_KEY não configurada"** | Falta o `config\.env` ou a linha da chave | Siga a [seção 2.3](#23-chave-da-api-do-gemini) |
| **"Modelo 'X' não disponível para esta chave"** | `GEMINI_MODEL` com nome errado | Deixe `GEMINI_MODEL=` vazio ou corrija o nome |
| Muitas linhas ✖ com **"Cota da API esgotada (429)"** | Limite por minuto estourado | Abaixe `GEMINI_RPM`, espere e reanalise as linhas com erro |
| ✖ **"Cota diária esgotada em todos os modelos"** | Nível gratuito; o limite do dia acabou | Tente no dia seguinte ou ative o faturamento |
| Linhas paradas em ⏳ por muito tempo | Modelos sobrecarregados ou sem cota; o programa está trocando de modelo | Olhe o aviso na barra de status. Para parar, **■ Cancelar** libera a janela na hora. |
| Linha ✖ **"PDF protegido por senha"** | O arquivo exige senha para abrir | Remova a senha em outro programa, ou edite o novo nome à mão |
| Linha ✖ **"Falha ao ler PDF"** | Arquivo corrompido ou não é PDF de verdade | Tente abri-lo com **📄 Abrir PDF**; se não abrir, o arquivo está danificado |
| Muitas linhas ⚠ | Documentos sem capa clara, slides, apostilas | Revise à mão ou use **Reanalisar com instrução** |
| Autor errado em tese (pegou o orientador) | Folha de rosto confusa | Reanalise com `o autor é o discente <nome>` |
| Título vem do periódico, não do artigo | Cabeçalho da revista na 1ª página | Reanalise com uma instrução ou edite o título |
| "Nenhum PDF encontrado" | Os PDFs estão em subpastas | Marque **Incluir subpastas** |
| Copiei e faltaram arquivos | Linhas ✖ ou ⏳ são puladas | O aviso de confirmação diz quantas; edite o novo nome delas para incluí-las |

---

## 13. Perguntas frequentes

**O programa apaga ou move meus PDFs?**
Não. Ele só lê os originais e cria cópias na pasta de saída.

**Posso rodar duas vezes na mesma pasta?**
Pode. A segunda vez usa o cache, é quase instantânea e não gasta cota. Na cópia, arquivos
que já existem na saída **não** são sobrescritos: as cópias novas ganham `(2)`, `(3)`…
Se não quiser duplicatas, esvazie a pasta de saída antes, ou escolha outra.

**Posso escolher uma pasta de rede ou pendrive?**
Pode. Qualquer pasta que o Windows consiga abrir.

**Todos os arquivos da pasta são copiados?**
Sim, inclusive os que não são PDF. As exceções: linhas que você tirou da tabela com
Delete, arquivos em subpastas quando "Incluir subpastas" está desmarcado, e falhas do
próprio Windows na cópia (arquivo aberto em outro programa, caminho longo demais, falta
de permissão), que aparecem no resumo e no log. Arquivos de sistema como `Thumbs.db` e
`desktop.ini` são ignorados.

**Os e-books ficam bons em PDF?**
O texto, as imagens e o sumário ficam corretos, em página A4. O visual é simples, como o de
um leitor de e-book. Livros com DRM (comprados em lojas como a da Amazon) não convertem. Os
PDFs convertidos ficam guardados em `.cache\convertidos`; pode apagar essa pasta quando
quiser liberar espaço.

**Funciona com PDF escaneado (foto de página)?**
Sim. O Gemini lê a imagem da página. A qualidade depende da nitidez do escaneamento.

**Funciona com PDFs em inglês ou espanhol?**
Sim. A área e o resumo saem em português; o título fica no idioma original.

**Por que a área às vezes não está na lista?**
A lista é só uma sugestão. A IA pode propor outra área, e você pode digitar qualquer uma.

**Dá para usar sem internet?**
Não para a análise, que precisa do Gemini. A cópia funciona offline, mas depende da análise.

---

## 14. Para desenvolvedores

> O porquê de cada escolha (arquitetura, bibliotecas, fluxo, ordem do código) está
> explicado em detalhes no [DECISOES.md](DECISOES.md).

### Estrutura

| Arquivo | Papel |
|---|---|
| `Renomeador.py` | Ponto de entrada; ajusta o `sys.path` e abre a janela |
| `gui.py` | A janela (Tkinter + `ttk.Treeview`) |
| `pipeline.py` | Análise paralela em segundo plano e fila de eventos para a janela |
| `gemini_client.py` | Conversa com o Gemini: cota, novas tentativas, troca de modelo, saída estruturada |
| `schema.py` | Formato da resposta pedida ao Gemini (Pydantic), montado com as categorias atuais |
| `listas.py` | Categorias e áreas editáveis, gravadas em `config\listas.json` |
| `dialogos.py` | Janelas do menu Configurações: editar listas e trocar a chave |
| `registro.py` | O log do programa (`logs\renomearpdf.log`) e o registro de erros não tratados |
| `pdf_tools.py` | Lista os arquivos da pasta; leitura local dos PDFs, recorte das primeiras páginas, hash |
| `conversao.py` | Conversão de EPUB, MOBI, AZW3 e FB2 para PDF (PyMuPDF) |
| `cache.py` | SQLite com as análises já feitas |
| `naming.py` | Modelo de nome e regras de nome de arquivo do Windows |
| `organizer.py` | Cópia sem sobrescrever, com log; separa o que vai para `.verificar` |
| `config.py` | Leitura do `config\.env` e gravação de valores nele (chave, Python) |
| `pythons.py` | Encontra e testa os Pythons do computador |
| `Iniciar.bat` | Inicializador para Windows: acha o Python, instala dependências, cria o `config\.env` |
| `tests/` | Testes automáticos, com um Gemini falso (não usam internet nem cota) |

### Rodar os testes

```powershell
python -m pytest tests -q
```

### Fluxo de uma análise

```text
e-book ─► converte para PDF (guardado em .cache\convertidos)
   │
   ▼
PDF ─► hash ─► está no cache? ──sim──► resultado (↺)
                    │não
                    ▼
          lê o PDF e recorta as primeiras páginas
                    │
                    ▼
          Gemini (PDF recortado; se ele recusar, vai só o texto)
                    │  erro passageiro ─► espera e tenta de novo
                    │  sem cota / fora do ar ─► troca de modelo
                    ▼
          guarda no cache ─► resultado (✔, ou ⚠ se a confiança for menor que 60%)
```

### O que não vai para o Git

`config/.env`, `config/listas.json`, `logs/`, `.cache/`, `PDFs/`, `out/`, `_old_/` e qualquer `*.pdf` estão no `.gitignore`. O `config/.env.example` vai, porque não tem chave.
