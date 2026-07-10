from __future__ import annotations

import re
from dataclasses import dataclass, field

HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,64}\b")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
PATH_RE = re.compile(r"(?:^|[\s\"'`=(])((?:/[^\s\"'`:]+|[A-Za-z]:\\[^\s\"'`]+|[\w.-]+/[\w./-]+))")
PORT_RE = re.compile(r"(?:(?:localhost|127\.0\.0\.1|0\.0\.0\.0)|:\s*|port[=:\s]+)(\d{2,5})\b", re.I)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ARN_RE = re.compile(r"\barn:aws:[^\s\"']+")
SECRETISH_RE = re.compile(r"\b(?:sk-|rk-|ghp_|xox[baprs]-)[A-Za-z0-9_\-]{8,}\b")


@dataclass
class FactSheet:
    hex_ids: list[str] = field(default_factory=list)
    uuids: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    arns: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            (self.hex_ids, self.uuids, self.paths, self.ports, self.emails, self.arns, self.secrets)
        )

    def format(self, limit: int = 80) -> str:
        lines = ["[oxpipe fact-sheet — exact tokens; prefer these over image OCR]"]

        def add(label: str, values: list[str]) -> None:
            seen: set[str] = set()
            for v in values:
                if v in seen:
                    continue
                seen.add(v)
                lines.append(f"{label}: {v}")
                if len(lines) > limit:
                    return

        add("uuid", self.uuids)
        add("hex", [h for h in self.hex_ids if h not in {u.replace("-", "") for u in self.uuids}])
        add("path", self.paths)
        add("port", self.ports)
        add("email", self.emails)
        add("arn", self.arns)
        add("secretish", self.secrets)
        if len(lines) == 1:
            lines.append("(none extracted)")
        return "\n".join(lines[: limit + 1])


def extract_factsheet(text: str) -> FactSheet:
    uuids = UUID_RE.findall(text)
    hex_ids = [h for h in HEX_RE.findall(text) if len(h) >= 8]
    paths = [m.group(1) for m in PATH_RE.finditer(text)]
    # Filter noisy short relative tokens
    paths = [p for p in paths if ("/" in p or "\\" in p) and len(p) >= 4][:40]
    ports = PORT_RE.findall(text)
    emails = EMAIL_RE.findall(text)
    arns = ARN_RE.findall(text)
    secrets = SECRETISH_RE.findall(text)
    return FactSheet(
        hex_ids=hex_ids[:40],
        uuids=uuids[:20],
        paths=paths,
        ports=list(dict.fromkeys(ports))[:20],
        emails=emails[:20],
        arns=arns[:20],
        secrets=secrets[:20],
    )


def looks_secretish(text: str) -> bool:
    return bool(SECRETISH_RE.search(text))
