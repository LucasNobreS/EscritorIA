import base64
import io
import unittest
import zipfile
import attachments
import gemini_text


class Multimodal(unittest.TestCase):
    def attachment(self, name, raw):
        return attachments.decode(
            [{"filename": name, "data": base64.b64encode(raw).decode()}]
        )[0]

    def test_binary_media_maps_to_native_inline_parts(self):
        for name, raw, mime in [
            ("foto.png", b"\x89PNG\r\n\x1a\nTEST", "image/png"),
            ("arquivo.pdf", b"%PDF-1.7 TEST", "application/pdf"),
            ("som.mp3", b"ID3TEST", "audio/mpeg"),
            ("video.mp4", b"ftypTEST", "video/mp4"),
        ]:
            item = self.attachment(name, raw)
            self.assertEqual(item["analysis_status"], "gemini")
            body = gemini_text.native_payload(
                [
                    {
                        "role": "user",
                        "content": "Analise",
                        "inline_files": [
                            {
                                "filename": name,
                                "mime": item["mime"],
                                "data": base64.b64encode(raw).decode(),
                            }
                        ],
                    }
                ],
                1024,
            )
            part = body["contents"][0]["parts"][-1]["inlineData"]
            self.assertEqual(part["mimeType"], mime)
            self.assertEqual(base64.b64decode(part["data"]), raw)

    def test_docx_xlsx_and_zip_extract_without_running_files(self):
        cases = [
            (
                "relatorio.docx",
                {"word/document.xml": "<document><p><t>Texto Word</t></p></document>"},
                "Texto Word",
            ),
            (
                "dados.xlsx",
                {
                    "xl/worksheets/sheet1.xml": '<worksheet><row><c r="A1" t="s"><v>0</v></c></row></worksheet>',
                    "xl/sharedStrings.xml": "<sst><si><t>Receita</t></si></sst>",
                },
                "A1=Receita",
            ),
            (
                "projeto.zip",
                {
                    "index.html": "<h1>Site existente</h1>",
                    "sub/script.py": 'print("não executar")',
                },
                "Site existente",
            ),
        ]
        for name, files, expected in cases:
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as z:
                for path, text in files.items():
                    z.writestr(path, text)
            item = self.attachment(name, out.getvalue())
            self.assertEqual(item["analysis_status"], "text")
            self.assertIn(expected, item["content"])

    def test_oversized_upload_is_rejected_and_archive_entities_not_expanded(self):
        with self.assertRaises(ValueError):
            self.attachment("large.bin", b"0" * (attachments.MAX_BYTES + 1))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr(
                "word/document.xml",
                '<!DOCTYPE x [<!ENTITY x "boom">]><document>&x;</document>',
            )
        item = self.attachment("x.docx", out.getvalue())
        self.assertEqual(item["analysis_status"], "unavailable")
        self.assertIn("entidades", item["content"])
