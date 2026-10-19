import zipfile

import pytest

from vkr_checker.docx.package import DocxError, DocxPackage, PackageLimits

CT = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
DOC = (
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p/></w:body></w:document>"
)


def make_zip(path, parts):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    return path


def good(tmp_path, **extra):
    return make_zip(
        tmp_path / "a.docx", {"[Content_Types].xml": CT, "word/document.xml": DOC, **extra}
    )


def code_of(path, limits=None):
    with pytest.raises(DocxError) as exc:
        DocxPackage.open(path, limits)
    return exc.value.code


def test_opens_valid_docx(tmp_path):
    with DocxPackage.open(good(tmp_path)) as pkg:
        assert pkg.has("word/document.xml")
        assert pkg.xml("word/document.xml").tag.endswith("document")
        assert pkg.names() == ["[Content_Types].xml", "word/document.xml"]


@pytest.mark.parametrize(
    "head", [b"%PDF-1.7 rest", b"{\\rtf1 abc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600]
)
def test_non_zip_signatures_are_unsupported_format(tmp_path, head):
    f = tmp_path / "x.docx"  # расширение .docx, но содержимое чужое
    f.write_bytes(head)
    assert code_of(f) == "unsupported_format"


def test_encrypted_ole_container_is_invalid_docx(tmp_path):
    f = tmp_path / "enc.docx"
    f.write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600 + "EncryptedPackage".encode("utf-16-le")
    )
    assert code_of(f) == "invalid_docx"


def test_empty_file_is_unsupported_format(tmp_path):
    f = tmp_path / "e.docx"
    f.write_bytes(b"")
    assert code_of(f) == "unsupported_format"


def test_zip_without_document_xml_is_unsupported_format(tmp_path):
    f = make_zip(tmp_path / "o.odt", {"content.xml": "<a/>", "mimetype": "x"})
    assert code_of(f) == "unsupported_format"


def test_truncated_zip_is_invalid_docx(tmp_path):
    f = good(tmp_path)
    f.write_bytes(f.read_bytes()[:-30])
    assert code_of(f) == "invalid_docx"


def test_too_many_entries(tmp_path):
    f = good(tmp_path, **{f"word/p{i}.xml": "<a/>" for i in range(10)})
    assert code_of(f, PackageLimits(max_entries=5)) == "docx_limits_exceeded"


def test_declared_unzipped_size_limit(tmp_path):
    f = good(tmp_path, **{"word/big.bin": "0" * 100_000})
    assert code_of(f, PackageLimits(max_unzipped_bytes=50_000)) == "docx_limits_exceeded"


def test_zip_bomb_detected_before_reading(tmp_path):
    f = good(tmp_path, **{"word/bomb.bin": b"\0" * 20_000_000})
    assert f.stat().st_size < 100_000
    assert code_of(f, PackageLimits(max_unzipped_bytes=1_000_000)) == "docx_limits_exceeded"


def test_read_budget_counts_actual_bytes(tmp_path):
    f = good(tmp_path, **{"word/a.bin": b"1" * 400, "word/b.bin": b"2" * 400})
    limits = PackageLimits(max_unzipped_bytes=len(DOC) + len(CT) + 800 + 5)
    with DocxPackage.open(f, limits) as pkg:
        pkg._limits = PackageLimits(max_unzipped_bytes=500)  # имитация лживых заголовков
        pkg.read("word/a.bin")
        with pytest.raises(DocxError) as exc:
            pkg.read("word/b.bin")
    assert exc.value.code == "docx_limits_exceeded"


@pytest.mark.parametrize("name", ["../evil.xml", "/abs.xml", "word/../../x.xml", "C:/x.xml"])
def test_dangerous_entry_names(tmp_path, name):
    f = good(tmp_path)
    with zipfile.ZipFile(f, "a") as zf:
        zf.writestr(name, "x")
    assert code_of(f) == "invalid_docx"


def test_broken_xml_part_is_invalid_docx(tmp_path):
    f = make_zip(tmp_path / "b.docx", {"word/document.xml": "<w:document"})
    with DocxPackage.open(f) as pkg, pytest.raises(DocxError) as exc:
        pkg.xml("word/document.xml")
    assert exc.value.code == "invalid_docx"


def test_doctype_and_entities_rejected(tmp_path):
    evil = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><d>&x;</d>'
    f = make_zip(tmp_path / "x.docx", {"word/document.xml": evil})
    with DocxPackage.open(f) as pkg, pytest.raises(DocxError) as exc:
        pkg.xml("word/document.xml")
    assert exc.value.code == "invalid_docx"


def test_relationships_marks_external(tmp_path):
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="t/styles" Target="styles.xml"/>'
        '<Relationship Id="rId2" Type="t/hyperlink" Target="http://x" TargetMode="External"/>'
        "</Relationships>"
    )
    f = good(tmp_path, **{"word/_rels/document.xml.rels": rels})
    with DocxPackage.open(f) as pkg:
        assert pkg.relationships() == {
            "rId1": ("t/styles", "styles.xml", False),
            "rId2": ("t/hyperlink", "http://x", True),
        }
