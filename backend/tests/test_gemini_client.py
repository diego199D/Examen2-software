"""Cliente Gemini centralizado: traducción de esquemas y reintentos. Nunca
toca la red (el transporte se reemplaza por un falso)."""

import pytest

from app.services.ai import gemini_client
from app.services.ai.gemini_client import IANoDisponibleError, esquema_gemini
from app.services.comandos_voz import construir_tools, construir_tools_voz


def _recorrer(esquema):
    yield esquema
    for v in (esquema.get("properties") or {}).values():
        yield from _recorrer(v)
    if "items" in esquema:
        yield from _recorrer(esquema["items"])


class TestEsquema:
    def test_nullable_y_enum_con_none(self):
        r = esquema_gemini({"type": ["string", "null"], "enum": ["1", "0..*", None]})
        assert r == {"type": "STRING", "nullable": True, "enum": ["1", "0..*"]}

    def test_quita_additional_properties_y_conserva_orden(self):
        r = esquema_gemini(
            {
                "type": "object",
                "properties": {"b": {"type": "string"}, "a": {"type": "integer"}},
                "required": ["b"],
                "additionalProperties": False,
            }
        )
        assert "additionalProperties" not in r
        assert r["property_ordering"] == ["b", "a"]
        assert r["properties"]["a"] == {"type": "INTEGER"}

    def test_objeto_sin_properties_falla_antes_de_llamar(self):
        with pytest.raises(ValueError):
            esquema_gemini({"type": "object"})

    def test_one_of_prohibido(self):
        with pytest.raises(ValueError):
            esquema_gemini({"oneOf": [{"type": "string"}]})

    @pytest.mark.parametrize("tools", [construir_tools(), construir_tools_voz()])
    def test_todas_las_tools_reales_son_validas_para_gemini(self, tools):
        from google.genai import types

        for t in tools:
            esquema = esquema_gemini(t["function"]["parameters"])
            types.Schema.model_validate(esquema)  # no lanza
            for nodo in _recorrer(esquema):
                assert "additionalProperties" not in nodo
                if nodo.get("type") == "OBJECT":
                    assert nodo.get("properties")




class TestReintentos:
    def _preparar(self, monkeypatch, fallos):
        from google.genai import errors

        llamadas = []

        class _Err(errors.APIError):
            def __init__(self, code):
                Exception.__init__(self, f"error {code}")
                self.code = code

        class _Modelos:
            def generate_content(self, model, contents, config):
                llamadas.append(model)
                if fallos:
                    raise _Err(fallos.pop(0))
                return "ok"

        class _Cliente:
            models = _Modelos()

        monkeypatch.setattr(gemini_client, "_cliente", lambda: _Cliente())
        monkeypatch.setattr(gemini_client.time, "sleep", lambda s: None)
        monkeypatch.setattr(gemini_client.settings, "GEMINI_FALLBACK_MODEL", "respaldo")
        return llamadas

    def test_429_se_reintenta_y_luego_funciona(self, monkeypatch):
        llamadas = self._preparar(monkeypatch, [429, 429])
        assert gemini_client._generar("principal", [], None) == "ok"
        assert llamadas == ["principal"] * 3

    def test_saturado_pasa_al_modelo_de_respaldo(self, monkeypatch):
        llamadas = self._preparar(monkeypatch, [503, 503, 503])
        assert gemini_client._generar("principal", [], None) == "ok"
        assert llamadas == ["principal"] * 3 + ["respaldo"]

    def test_agotado_da_mensaje_claro(self, monkeypatch):
        self._preparar(monkeypatch, [429] * 10)
        with pytest.raises(IANoDisponibleError) as exc:
            gemini_client._generar("principal", [], None)
        assert "límite" in str(exc.value)

    def test_error_400_no_se_reintenta(self, monkeypatch):
        llamadas = self._preparar(monkeypatch, [400])
        with pytest.raises(IANoDisponibleError):
            gemini_client._generar("principal", [], None)
        assert llamadas == ["principal"]

    def test_sin_api_key(self, monkeypatch):
        monkeypatch.setattr(gemini_client.settings, "GEMINI_API_KEY", None)
        with pytest.raises(IANoDisponibleError):
            gemini_client._cliente()
