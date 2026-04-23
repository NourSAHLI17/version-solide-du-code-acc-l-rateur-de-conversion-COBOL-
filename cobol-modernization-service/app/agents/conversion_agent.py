"""LLM-backed conversion agent for Java generation."""

import json
import os
from typing import Dict, Tuple

import httpx
from dotenv import load_dotenv

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover - optional runtime dependency
    ChatGoogleGenerativeAI = None

try:
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:  # pragma: no cover - optional runtime dependency
    try:
        from langchain.prompts import ChatPromptTemplate
    except ImportError:  # pragma: no cover - optional runtime dependency
        ChatPromptTemplate = None


load_dotenv()


class ConversionAgent:
    """
    Build and execute behavior-preserving Java conversion prompts.

    Example:
        Input:
            source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
        Output:
            "// Conversion agent is not configured...." or generated Java source.
    """

    def __init__(self):
        self.llm = None
        self.provider = "stub"
        self.model_name = "gemini-2.0-flash"
        self.openai_base_url = "https://api.openai.com/v1/chat/completions"
        self.openrouter_base_url = "https://openrouter.ai/api/v1/chat/completions"
        provider_preference = os.getenv("LLM_PROVIDER", "auto").lower()
        google_api_key = os.getenv("GOOGLE_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        if provider_preference in {"auto", "google"} and ChatGoogleGenerativeAI and google_api_key:
            self.llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=0,
                google_api_key=google_api_key,
            )
            self.provider = "google"
        elif provider_preference in {"auto", "openai"} and openai_api_key:
            self.provider = "openai"
            self.model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            self.llm = object()
        elif provider_preference in {"auto", "openrouter"} and openrouter_api_key:
            self.provider = "openrouter"
            self.model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            self.llm = object()

    def convert(self, source_code: str, parser_output: dict, analysis_output: str) -> str:
        """
        Convert COBOL plus parser and analysis context into Java code.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Deterministic parser-layer JSON.
            analysis_output: Semantic analysis as JSON string or dictionary.

        Returns:
            Generated Java code or a stub if the LLM is not configured.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
            Output:
                "public class ..." or configuration stub text
        """

        if self.provider == "openai":
            prompt, prompt_input = self.build_conversion_prompt_input(
                source_code,
                parser_output,
                analysis_output,
            )
            return self._convert_with_openai(prompt, prompt_input)

        if self.provider == "openrouter":
            prompt, prompt_input = self.build_conversion_prompt_input(
                source_code,
                parser_output,
                analysis_output,
            )
            return self._convert_with_openrouter(prompt, prompt_input)

        if not self.llm or not ChatPromptTemplate:
            return (
                "// Conversion agent is not configured.\n"
                "// Provide GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY to enable Java generation.\n"
            )

        prompt, prompt_input = self.build_conversion_prompt_input(
            source_code,
            parser_output,
            analysis_output,
        )
        chain = prompt | self.llm
        response = chain.invoke(prompt_input)
        return response.content

    def get_runtime_status(self) -> Dict[str, object]:
        """
        Report conversion-agent runtime readiness without triggering an LLM call.

        Returns:
            A lightweight status object describing LLM availability and model info.

        Example:
            Input:
                ConversionAgent().get_runtime_status()
            Output:
                {"llm_configured": True, "model_name": "gemini-2.0-flash", ...}
        """

        return {
            "llm_configured": self.llm is not None,
            "provider": self.provider,
            "model_name": self.model_name,
            "prompt_template_available": ChatPromptTemplate is not None,
        }

    def build_conversion_prompt_input(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
    ) -> Tuple[object, Dict[str, str]]:
        """
        Build the prompt and normalized input payload for Java conversion.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Parser-layer JSON.
            analysis_output: Analysis JSON string or dictionary.

        Returns:
            A tuple of `(prompt_template, prompt_input_dict)`.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
            Output:
                (<ChatPromptTemplate>, {"source": "...", "parser_json": "...", ...})
        """

        normalized_analysis = self._normalize_analysis_output(analysis_output)
        config = self._default_conversion_config(parser_output, normalized_analysis)
        parser_json = json.dumps(parser_output, indent=2, sort_keys=True)
        analysis_json = json.dumps(normalized_analysis, indent=2, sort_keys=True)
        context_mode = self._describe_context_mode(parser_output, normalized_analysis)
        prompt = ChatPromptTemplate.from_template(
            """
You are the Conversion Agent of a COBOL modernization system.

Your role is to transform COBOL source code, parser-derived structure,
and semantic analysis into reliable, behavior-preserving Java code.

You are not allowed to:
- invent logic not present in the inputs
- weaken or simplify business rules
- ignore parser or analysis constraints
- use float or double for monetary or implied-decimal values

Core principle:
Behavior preservation is more important than syntax mirroring.

INPUTS:

### Raw COBOL Source
{source}

### Context Mode
{context_mode}

### Parser Output
{parser_json}

### Analysis Output
{analysis_json}

### Conversion Configuration
{conversion_config}

CONVERSION RULES:
1. Preserve business behavior exactly as defined by the parser and analysis inputs.
   If Parser Output or Analysis Output is empty, use only the context that is present
   plus the Raw COBOL Source. Do not invent missing parser or analysis facts.
2. Use BigDecimal for COMP-3 fields and any numeric field with implied decimal.
3. Map COBOL paragraphs or major logic blocks to Java methods when appropriate.
4. Convert PERFORM to structured loops or method calls.
5. Convert EVALUATE to switch or explicit if/else chains.
6. Preserve external calls, file I/O sequencing, and dependency boundaries.
7. Convert OCCURS to arrays or collections only when behavior is preserved.
8. Convert REDEFINES carefully; document any union-like handling in mapping notes.
9. Refactor GO TO into structured control flow while preserving decision order.
10. Avoid JOBOL: no monolithic class, no COBOL-style variable names in
    final Java API, and no global mutable procedural dump.

OUTPUT FORMAT:
- Return Java source code first.
- After the code, include a section titled exactly: ## MAPPING NOTES
- In mapping notes, list:
  - COBOL paragraph/block to Java method mappings
  - assumptions made
  - uncertainties or areas requiring human review

QUALITY BAR:
- idiomatic Java
- conversion-ready
- behavior-preserving
- traceable to source structure
"""
        )
        return prompt, {
            "source": source_code,
            "context_mode": context_mode,
            "parser_json": parser_json,
            "analysis_json": analysis_json,
            "conversion_config": json.dumps(config, indent=2, sort_keys=True),
        }

    def _convert_with_openrouter(self, prompt: object, prompt_input: Dict[str, str]) -> str:
        """
        Invoke OpenRouter's OpenAI-compatible chat completions endpoint.

        Args:
            prompt: Prompt template used for conversion.
            prompt_input: Formatted prompt variables.

        Returns:
            Generated Java code plus mapping notes from the remote model.

        Example:
            Input:
                prompt=<ChatPromptTemplate>, prompt_input={"source": "..."}
            Output:
                "public class ConvertedProgram { ... }"
        """

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return (
                "// Conversion agent is not configured.\n"
                "// Provide GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY to enable Java generation.\n"
            )

        rendered_prompt = self._render_prompt_for_openrouter(prompt, prompt_input)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "cobol-modernization-service"),
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": rendered_prompt}],
            "temperature": 0,
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.openrouter_base_url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                raise RuntimeError(
                    f"OpenRouter request failed with status {response.status_code}: {detail}"
                ) from exc
            body = response.json()

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenRouter response did not include a chat completion payload.") from exc

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            if parts:
                return "\n".join(parts)
        raise ValueError("OpenRouter response content format was not recognized.")

    def _convert_with_openai(self, prompt: object, prompt_input: Dict[str, str]) -> str:
        """
        Invoke OpenAI's chat completions endpoint for Java conversion.

        Args:
            prompt: Prompt template used for conversion.
            prompt_input: Formatted prompt variables.

        Returns:
            Generated Java code plus mapping notes from the remote model.

        Example:
            Input:
                prompt=<ChatPromptTemplate>, prompt_input={"source": "..."}
            Output:
                "public class ConvertedProgram { ... }"
        """

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return (
                "// Conversion agent is not configured.\n"
                "// Provide GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY to enable Java generation.\n"
            )

        rendered_prompt = self._render_prompt_for_openrouter(prompt, prompt_input)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": rendered_prompt}],
            "temperature": 0,
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.openai_base_url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                raise RuntimeError(
                    f"OpenAI request failed with status {response.status_code}: {detail}"
                ) from exc
            body = response.json()

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenAI response did not include a chat completion payload.") from exc

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            if parts:
                return "\n".join(parts)
        raise ValueError("OpenAI response content format was not recognized.")

    def _render_prompt_for_openrouter(self, prompt: object, prompt_input: Dict[str, str]) -> str:
        """
        Render a LangChain prompt into a single string for OpenRouter transport.

        Args:
            prompt: Prompt template instance.
            prompt_input: Variables used to render the prompt.

        Returns:
            A single string containing the full conversion instruction.

        Example:
            Input:
                prompt=<ChatPromptTemplate>, prompt_input={"source": "PROCEDURE DIVISION."}
            Output:
                "You are the Conversion Agent ..."
        """

        if hasattr(prompt, "format_messages"):
            messages = prompt.format_messages(**prompt_input)
            return "\n\n".join(str(message.content) for message in messages)
        if hasattr(prompt, "format"):
            return str(prompt.format(**prompt_input))
        return str(prompt)

    def _normalize_analysis_output(self, analysis_output: str) -> Dict[str, object]:
        """
        Normalize analysis output into a dictionary for prompt construction.

        Example:
            Input:
                '{"complexity": "simple"}'
            Output:
                {"complexity": "simple"}
        """

        if isinstance(analysis_output, dict):
            return analysis_output
        if not analysis_output:
            return {}
        if isinstance(analysis_output, str):
            cleaned = analysis_output.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {"raw_analysis": analysis_output}

    def _default_conversion_config(
        self,
        parser_output: Dict[str, object],
        analysis_output: Dict[str, object],
    ) -> Dict[str, object]:
        """
        Build default conversion configuration hints for the LLM.

        Example:
            Input:
                parser_output={"program_name": "TXNPROC", "dependencies": {"files": []}},
                analysis_output={"complexity": "simple"}
            Output:
                {"target_language": "java", "package_name": "com.modernized.txnproc", ...}
        """

        program_name = (
            analysis_output.get("program_name")
            or parser_output.get("program_name")
            or "modernized"
        )
        package_suffix = str(program_name).lower().replace("-", "")
        complexity = analysis_output.get("complexity", "simple")
        dependencies = parser_output.get("dependencies", {})
        has_files = bool(dependencies.get("files"))

        return {
            "target_language": "java",
            "java_version": "17",
            "framework": "spring-boot" if has_files else "none",
            "package_name": f"com.modernized.{package_suffix}",
            "naming_style": "camelCase",
            "decimal_strategy": "bigdecimal",
            "preferred_decimal_java_type": "BigDecimal",
            "io_strategy": "buffered" if has_files else "in-memory",
            "generate_tests": True,
            "complexity_hint": complexity,
        }

    def _describe_context_mode(
        self,
        parser_output: Dict[str, object],
        analysis_output: Dict[str, object],
    ) -> str:
        has_parser = bool(parser_output)
        has_analysis = bool(analysis_output)
        if has_parser and has_analysis:
            return "COBOL source + parser output + analysis output"
        if has_parser:
            return "COBOL source + parser output only"
        if has_analysis:
            return "COBOL source + analysis output only"
        return "COBOL source only"
