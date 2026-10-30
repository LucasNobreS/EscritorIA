"""Validated UTF-8 source attachments. Originals are separate from generated outputs."""

import base64
import re
import io
import zipfile
from xml.etree import ElementTree as ET

EXTENSIONS = {
    "html",
    "htm",
    "css",
    "js",
    "mjs",
    "ts",
    "tsx",
    "jsx",
    "py",
    "sql",
    "json",
    "csv",
    "tsv",
    "txt",
    "md",
    "svg",
    "xml",
    "yaml",
    "yml",
    "toml",
    "ini",
    "log",
}
MAX_FILES = 6
MAX_TEXT = 60000
MAX_BYTES = 10 * 1024 * 1024


def decode(items):
    if not isinstance(items, list) or len(items) > MAX_FILES:
        raise ValueError("Anexe até seis arquivos por mensagem.")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Anexo inválido.")
        name = str(item.get("filename", "")).strip()
        if (
            not name
            or len(name) > 120
            or re.search(r'[\x00-\x1f\\/:*?"<>|]', name)
            or ".." in name
        ):
            raise ValueError("Nome de anexo inválido; envie apenas o nome, sem pastas.")
        encoded = item.get("data", "")
        if not isinstance(encoded, str) or len(encoded) > 14000000:
            raise ValueError("Anexo grande demais.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ValueError("Anexo corrompido durante o envio.") from None
        if len(raw) > MAX_BYTES:
            raise ValueError("Use no máximo 10 MB por arquivo.")
        content, mime, status = extract(name, raw)
        out.append(
            {
                "filename": name,
                "content": content,
                "data": raw,
                "mime": mime,
                "analysis_status": status,
            }
        )
    validate(out)
    return out


def validate(items):
    if sum(len(i["data"]) for i in items) > MAX_BYTES:
        raise ValueError("Os anexos juntos devem ter até 10 MB.")
    if len(items) > MAX_FILES:
        raise ValueError("Use até seis anexos, contando os reutilizados.")
    if sum(len(i["content"]) for i in items) > MAX_TEXT:
        raise ValueError(
            "Os anexos juntos devem ter até 60.000 caracteres. Divida o projeto em partes."
        )
    names = [i["filename"].casefold() for i in items]
    if len(set(names)) != len(names):
        raise ValueError(
            "Há anexos com nomes repetidos; renomeie os arquivos ou remova a repetição."
        )


def extract(name, raw):
    ext = name.rsplit(".", 1)[-1].lower()
    if raw.startswith(b"%PDF-"):
        return (
            "PDF original disponível para análise visual no Gemini.",
            "application/pdf",
            "gemini",
        )
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return (
            "Imagem PNG disponível para análise visual no Gemini.",
            "image/png",
            "gemini",
        )
    if raw.startswith(b"\xff\xd8"):
        return (
            "Imagem JPEG disponível para análise visual no Gemini.",
            "image/jpeg",
            "gemini",
        )
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return (
            "Imagem WebP disponível para análise visual no Gemini.",
            "image/webp",
            "gemini",
        )
    media = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
    }
    if ext in media:
        return (
            "Mídia disponível para análise no Gemini; duração e formato sujeitos aos limites do modelo.",
            media[ext],
            "gemini",
        )
    if raw.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                entries = z.infolist()
                if (
                    len(entries) > 1000
                    or sum(f.file_size for f in entries) > 15 * 1024 * 1024
                ):
                    raise ValueError(
                        "Arquivo compactado excede os limites de extração."
                    )
                shared = []
                if ext == "xlsx" and "xl/sharedStrings.xml" in z.namelist():
                    info = z.getinfo("xl/sharedStrings.xml")
                    if info.file_size > 2 * 1024 * 1024:
                        raise ValueError(
                            "Tabela de textos da planilha excede o limite."
                        )
                    data = z.read(info)
                    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                        raise ValueError("XML com entidades não é extraído.")
                    shared = ["".join(n.itertext()) for n in ET.fromstring(data)]
                parts = []
                for f in entries:
                    if f.is_dir():
                        continue
                    if f.flag_bits & 1:
                        raise ValueError(
                            "Arquivo protegido por senha; remova a proteção para análise."
                        )
                    if f.file_size > 2 * 1024 * 1024:
                        parts.append(
                            f"[Arquivo {f.filename}: grande demais para extração]"
                        )
                        continue
                    if ext in ("docx", "pptx", "xlsx", "odt", "ods", "odp"):
                        if not f.filename.endswith(".xml"):
                            continue
                        if ext == "docx" and not re.fullmatch(
                            r"word/(document|header[0-9]*|footer[0-9]*|footnotes|endnotes).xml",
                            f.filename,
                        ):
                            continue
                        if ext == "pptx" and not re.fullmatch(
                            r"ppt/slides/slide[0-9]+.xml", f.filename
                        ):
                            continue
                        if ext == "xlsx" and not (
                            f.filename.startswith("xl/worksheets/")
                            or f.filename == "xl/sharedStrings.xml"
                        ):
                            continue
                        if ext.startswith("od") and f.filename != "content.xml":
                            continue
                        data = z.read(f)
                        if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                            raise ValueError("XML com entidades não é extraído.")
                        root = ET.fromstring(data)
                        if ext == "xlsx":
                            if f.filename.endswith("sharedStrings.xml"):
                                shared = ["".join(n.itertext()) for n in root]
                                parts.append("Tabela de textos: " + str(shared))
                                continue
                            rows = []
                            for row in root.iter():
                                if row.tag.rsplit("}", 1)[-1] == "row":
                                    cells = []
                                    for cell in row:
                                        value = "".join(cell.itertext())
                                        if cell.get("t") == "s":
                                            try:
                                                value = shared[int(value)]
                                            except (
                                                ValueError,
                                                IndexError,
                                                UnboundLocalError,
                                            ):
                                                value = (
                                                    "[índice sharedStrings "
                                                    + value
                                                    + "]"
                                                )
                                        cells.append(
                                            str(cell.get("r", "")) + "=" + value
                                        )
                                    rows.append(" | ".join(cells))
                            parts.append(f.filename + "\n" + "\n".join(rows))
                        else:
                            parts.append(
                                f.filename
                                + "\n"
                                + "\n".join(
                                    n.text
                                    for n in root.iter()
                                    if n.tag.rsplit("}", 1)[-1] in ("t", "p", "h")
                                    and n.text
                                )
                            )
                    else:
                        parts.append("Arquivo no ZIP: " + f.filename)
                        if f.filename.rsplit(".", 1)[-1].lower() in EXTENSIONS:
                            try:
                                parts.append(z.read(f).decode("utf-8-sig"))
                            except UnicodeDecodeError:
                                parts.append("[Texto sem codificação UTF-8]")
                        else:
                            parts.append(
                                "[Conteúdo binário não interpretado dentro do ZIP; anexe separadamente para análise multimodal.]"
                            )
                    if sum(map(len, parts)) > MAX_TEXT:
                        break
                text = "\n".join(parts)
                if len(text) > MAX_TEXT:
                    text = (
                        text[: MAX_TEXT - 100]
                        + "\n[Extração parcial: limite de 60 mil caracteres atingido.]"
                    )
                return (
                    text or "[Arquivo compactado sem texto extraível]",
                    "application/zip",
                    "text",
                )
        except (
            ValueError,
            zipfile.BadZipFile,
            ET.ParseError,
            RuntimeError,
            NotImplementedError,
            OSError,
        ) as ex:
            return (
                "Não foi possível extrair: " + str(ex)[:200],
                "application/octet-stream",
                "unavailable",
            )
    try:
        text = raw.decode("utf-8-sig")
        if text.strip() and "\x00" not in text:
            return text, "text/plain", "text"
    except UnicodeDecodeError:
        pass
    return (
        "Arquivo original preservado. Este formato não possui leitor compatível nesta versão. Solicite uma conversão para formato aberto; não invente análise do conteúdo.",
        "application/octet-stream",
        "unavailable",
    )
