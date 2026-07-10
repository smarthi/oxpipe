from __future__ import annotations

from oxpipe.transform.factsheet import extract_factsheet


def test_extract_hex_uuid_path_port():
    text = """
    id=c7a1e90b4d2fabcd
    uuid=550e8400-e29b-41d4-a716-446655440000
    path=/srv/app/config/runtime.json
    listen port: 47822
    contact=dev@example.com
    """
    fs = extract_factsheet(text)
    assert any("c7a1e90b4d2fabcd" == h for h in fs.hex_ids)
    assert "550e8400-e29b-41d4-a716-446655440000" in fs.uuids
    assert any("runtime.json" in p for p in fs.paths)
    assert "47822" in fs.ports
    assert "dev@example.com" in fs.emails
    sheet = fs.format()
    assert "fact-sheet" in sheet
    assert "47822" in sheet
