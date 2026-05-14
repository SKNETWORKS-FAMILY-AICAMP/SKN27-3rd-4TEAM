"""Top-level user input supervisor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputDecision:
    input_type: str
    reason: str


class UserInputSupervisor:
    """Classifies user input before it enters document or chat flows."""

    DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".txt")

    def classify(self, filename: str | None = None, message: str | None = None) -> InputDecision:
        if filename:
            lower = filename.lower()
            if lower.endswith(self.DOCUMENT_EXTENSIONS):
                return InputDecision(input_type="document", reason="supported_contract_file")
            return InputDecision(input_type="unsupported_file", reason="unsupported_file_extension")
        if message and message.strip():
            return InputDecision(input_type="question", reason="text_question")
        return InputDecision(input_type="unknown", reason="empty_input")
