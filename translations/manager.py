import json
import os

from PyQt6.QtCore import QObject, pyqtSignal


class TranslationManager(QObject):
    language_changed = pyqtSignal(str)

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._dir = os.path.dirname(os.path.abspath(__file__))
        self._strings: dict[str, str] = {}
        self._current_lang = "en"

    def load(self, lang: str) -> bool:
        path = os.path.join(self._dir, f"{lang}.json")
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._strings = json.load(f)
            self._current_lang = lang
            self.language_changed.emit(lang)
            return True
        except Exception:
            return False

    @property
    def current_language(self) -> str:
        return self._current_lang

    _LANG_NAMES = {
        "en": "English",
        "zh_CN": "简体中文",
    }

    @property
    def available_languages(self) -> list[str]:
        langs = []
        if not os.path.isdir(self._dir):
            return langs
        for fname in os.listdir(self._dir):
            if fname.endswith(".json"):
                langs.append(fname[:-5])
        return sorted(langs)

    @classmethod
    def get_available_languages(cls) -> list[tuple[str, str]]:
        inst = cls.instance()
        codes = inst.available_languages
        return [(code, cls._LANG_NAMES.get(code, code)) for code in codes]

    def set_language(self, lang: str) -> None:
        self.load(lang)

    def tr(self, key: str, default: str = None, **kwargs) -> str:
        text = self._strings.get(key)
        if text is None:
            text = default if default is not None else key
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text


_TRANSLATOR = None


def tr(key: str, default: str = None, **kwargs) -> str:
    global _TRANSLATOR
    if _TRANSLATOR is None:
        _TRANSLATOR = TranslationManager.instance()
    return _TRANSLATOR.tr(key, default, **kwargs)
