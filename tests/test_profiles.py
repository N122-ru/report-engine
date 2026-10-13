import json

import pytest

from backend.app.engine.profile import PROFILE_FORMAT, PROFILE_VERSION, load_profile_input, validate_profile


def sample_profile():
    return {
        "format": PROFILE_FORMAT,
        "version": PROFILE_VERSION,
        "subject": {
            "id": "subj_networks",
            "name": "Сетевые технологии",
            "institute": "Институт технологий",
            "department": "Кафедра сетей",
            "teachers": [{"fio": "И.И. Иванов", "role": "доцент"}],
            "custom_instructions": "Сохранять номера команд без изменений.",
            "last_work_number": 4,
        },
        "meta": {
            "university": "Учебный университет",
            "ministry": "Министерство образования",
            "logo_mode": "none",
            "city": "Москва",
            "institute": "Институт технологий",
            "department": "Кафедра сетей",
            "doc_type": "ОТЧЕТ",
            "work_type": "о выполнении лабораторной работы",
            "work_number": 5,
            "discipline": "Сетевые технологии",
            "students": [{"fio": "П.П. Петров", "group": "ИВТ-101"}],
            "teachers": [{"fio": "И.И. Иванов", "role": "доцент"}],
            "year": 2026,
        },
    }


def test_profile_validation_and_metadata_mapping():
    profile = validate_profile(sample_profile())
    assert profile["subject"]["last_work_number"] == 4
    assert profile["meta"]["work_type"].startswith("о выполнении")


@pytest.mark.parametrize(
    "profile, message",
    [
        ({"format": "report-engine-project", "version": 1}, "формат"),
        ({"format": PROFILE_FORMAT, "version": 2}, "версия"),
        ({"format": PROFILE_FORMAT, "version": 1, "subject": {}, "meta": {}}, "повреждён"),
    ],
)
def test_profile_validation_rejects_invalid_input(profile, message):
    with pytest.raises(ValueError, match=message):
        validate_profile(profile)


def test_profile_file_input_resolves_relative_to_current_working_directory(tmp_path, monkeypatch):
    source = tmp_path / "profile.json"
    source.write_text(json.dumps(sample_profile(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    loaded = load_profile_input({"file_path": "profile.json"})

    assert loaded["subject"]["name"] == "Сетевые технологии"


def test_profile_file_input_rejects_corrupt_json(tmp_path):
    source = tmp_path / "profile.json"
    source.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="повреждён"):
        load_profile_input({"file_path": str(source)})
