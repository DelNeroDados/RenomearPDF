from naming import caminho_livre, finalizar_nome, montar_nome

M = "{area}-{sobrenome}-{ano}-{titulo}"


def test_monta_completo():
    n = montar_nome(M, {"area": "Física", "sobrenome": "silva", "ano": "2020",
                        "titulo": "ensino de física quântica com DNA"})
    assert n == "Física-Silva-2020-Ensino de física quântica com DNA.pdf"


def test_campos_vazios_nao_deixam_separador_duplo():
    n = montar_nome(M, {"area": "Física", "sobrenome": "", "ano": "", "titulo": "Óptica"})
    assert n == "Física-Óptica.pdf"


def test_tudo_vazio():
    assert montar_nome(M, {}) == "Sem titulo.pdf"


def test_caracteres_invalidos_e_reservados():
    assert finalizar_nome('a:b/c?"d*.pdf') == "a b c d.pdf"
    assert finalizar_nome("CON") == "_CON.pdf"
    assert finalizar_nome("titulo. ") == "titulo.pdf"


def test_tamanho_maximo():
    assert len(finalizar_nome("x" * 500)) == 150 + 4


def test_caminho_livre_nao_sobrescreve(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"")
    res = set()
    assert caminho_livre(tmp_path, "a.pdf", res).name == "a (2).pdf"
    assert caminho_livre(tmp_path, "a.pdf", res).name == "a (3).pdf"
    assert caminho_livre(tmp_path, "A.pdf", res).name == "A (4).pdf"
