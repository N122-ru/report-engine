import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  PROFILE_FORMAT,
  PROFILE_VERSION,
  createProfile,
  parseProfile,
  serializeProfile,
} from './profiles.ts';

const subject = {
  id: 'subj_networks',
  name: 'Сетевые технологии',
  institute: 'Институт технологий',
  department: 'Кафедра сетей',
  teachers: [{ fio: 'И.И. Иванов', role: 'доцент' }],
  custom_instructions: 'Сохранять номера команд без изменений.',
  last_work_number: 4,
};

const metadata = {
  university: 'Учебный университет',
  ministry: 'Министерство образования',
  logo_mode: 'none',
  city: 'Москва',
  institute: subject.institute,
  department: subject.department,
  doc_type: 'ОТЧЕТ',
  work_type: 'о выполнении лабораторной работы',
  work_number: 5,
  discipline: subject.name,
  students: [{ fio: 'П.П. Петров', group: 'ИВТ-101' }, { fio: 'А.А. Сидорова', group: 'ИВТ-101' }],
  teachers: subject.teachers,
  year: 2026,
};

test('profile serialization round-trips subject and title-page requisites', () => {
  const profile = createProfile(subject, metadata);
  const parsed = parseProfile(JSON.parse(serializeProfile(profile)));

  assert.equal(parsed.format, PROFILE_FORMAT);
  assert.equal(parsed.version, PROFILE_VERSION);
  assert.deepEqual(parsed.subject, subject);
  assert.deepEqual(parsed.meta, metadata);
});

test('profile validation reports wrong format and unsupported version', () => {
  assert.throws(
    () => parseProfile({ format: 'report-engine-project', version: 1 }),
    /Неверный формат файла профиля/,
  );
  assert.throws(
    () => parseProfile({ format: PROFILE_FORMAT, version: 99 }),
    /Неподдерживаемая версия профиля/,
  );
});

test('profile validation rejects a malformed JSON shape', () => {
  assert.throws(
    () => parseProfile({ format: PROFILE_FORMAT, version: PROFILE_VERSION, subject, meta: { ...metadata, students: [] } }),
    /Профиль повреждён/,
  );
});
