import React, { useEffect, useRef, useState } from 'react';
import { ReportMetadata, StudentInfo, TeacherInfo, TEACHER_ROLES, LogoMode, ReferenceItem, REFERENCE_KINDS, emptyReference } from '../types';
import { formatReference } from '../services/bibliography';
import { 
  GraduationCap, Users, Plus, Trash2, 
  Check, BookOpen, School, Settings2
} from 'lucide-react';
import { 
  getGlobalProfile, saveGlobalProfile, 
  getSubjectPresets, saveSubjectPresets, 
  createNewSubjectPreset, normalizeLogoMode, SubjectPreset 
} from '../services/profiles';

interface MetadataFormProps {
  meta: ReportMetadata;
  onChange: (updated: ReportMetadata) => void;
  activeSubjectId: string;
  onSubjectChange: (id: string) => void;
  subjectPresets?: SubjectPreset[];
  onPresetsChange?: (presets: SubjectPreset[]) => void;
  onDeletePreset?: (id: string) => void;
}

export const MetadataForm: React.FC<MetadataFormProps> = ({ 
  meta, 
  onChange,
  activeSubjectId,
  onSubjectChange,
  subjectPresets: propPresets,
  onPresetsChange,
  onDeletePreset
}) => {
  const [activeTab, setActiveTab] = useState<'subject' | 'university' | 'work'>('subject');
  const [localPresets, setLocalPresets] = useState<SubjectPreset[]>(() => getSubjectPresets());
  const subjectPresets = propPresets || localPresets;
  const setSubjectPresets = (updated: SubjectPreset[]) => {
    if (onPresetsChange) {
      onPresetsChange(updated);
    } else {
      setLocalPresets(updated);
    }
    saveSubjectPresets(updated);
  };
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const statusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
  }, []);

  const showStatus = (msg: string) => {
    if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
    setStatusMsg(msg);
    statusTimerRef.current = setTimeout(() => {
      setStatusMsg(null);
      statusTimerRef.current = null;
    }, 2500);
  };

  const updateField = <K extends keyof ReportMetadata>(field: K, val: ReportMetadata[K]) => {
    onChange({ ...meta, [field]: val });
  };

  // Update the teacher list.
  const handleTeacherChange = (index: number, field: keyof TeacherInfo, value: string) => {
    const list = [...(meta.teachers || [])];
    list[index] = { ...list[index], [field]: value };
    updateField('teachers', list);
  };

  const handleAddTeacher = () => {
    const list = [...(meta.teachers || [])];
    list.push({ fio: '', role: 'преп.' });
    updateField('teachers', list);
  };

  const handleRemoveTeacher = (index: number) => {
    const list = (meta.teachers || []).filter((_, i) => i !== index);
    updateField('teachers', list.length > 0 ? list : [{ fio: '', role: 'преп.' }]);
  };

  // Update the student list.
  const handleStudentChange = (index: number, field: keyof StudentInfo, value: string) => {
    const list = [...(meta.students || [])];
    list[index] = { ...list[index], [field]: value };
    updateField('students', list);
  };

  const handleAddStudent = () => {
    const list = [...(meta.students || [])];
    list.push({ fio: '', group: list[0]?.group || '' });
    updateField('students', list);
  };

  const handleRemoveStudent = (index: number) => {
    const list = (meta.students || []).filter((_, i) => i !== index);
    updateField('students', list.length > 0 ? list : [{ fio: '', group: '' }]);
  };

  // Bibliography entries.
  const handleRefChange = (index: number, field: keyof ReferenceItem, value: string) => {
    const list = [...(meta.references || [])];
    list[index] = { ...list[index], [field]: value } as ReferenceItem;
    updateField('references', list);
  };

  const handleAddRef = () => {
    updateField('references', [...(meta.references || []), emptyReference()]);
  };

  const handleRemoveRef = (index: number) => {
    updateField('references', (meta.references || []).filter((_, i) => i !== index));
  };

  // Save department and teacher settings to the subject preset.
  const handleSaveCurrentAsPreset = () => {
    const currentName = meta.discipline.trim() || 'Новая дисциплина';
    const existingIndex = subjectPresets.findIndex(p => p.id === activeSubjectId);
    
    let updated: SubjectPreset[];
    let targetSubjectId = activeSubjectId;
    if (existingIndex >= 0) {
      updated = [...subjectPresets];
      updated[existingIndex] = {
        ...updated[existingIndex],
        name: currentName,
        institute: meta.institute,
        department: meta.department,
        teachers: meta.teachers,
        custom_instructions: meta.custom_instructions
      };
      targetSubjectId = updated[existingIndex].id;
      showStatus(`Шаблон «${currentName}» обновлён`);
    } else {
      const newPreset: SubjectPreset = {
        id: `subj_${Date.now()}`,
        name: currentName,
        institute: meta.institute,
        department: meta.department,
        teachers: meta.teachers,
        custom_instructions: meta.custom_instructions
      };
      updated = [...subjectPresets, newPreset];
      targetSubjectId = newPreset.id;
      showStatus(`Создан новый шаблон «${currentName}»`);
    }

    setSubjectPresets(updated);
    if (targetSubjectId !== activeSubjectId) onSubjectChange(targetSubjectId);
  };

  // Save the global university profile.
  const handleSaveGlobalProfile = () => {
    saveGlobalProfile({
      university: meta.university,
      ministry: meta.ministry || "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ",
      city: meta.city,
      logo_mode: normalizeLogoMode(meta.logo_mode),
      custom_logo: meta.custom_logo,
      default_student: meta.students[0] || { fio: "", group: "" }
    });
    showStatus("Глобальный профиль вуза сохранён");
  };

  const handleCustomLogoFile = async (file?: File | null) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      showStatus("Логотип слишком велик (максимум 2 МБ)");
      return;
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    const isPng = bytes.length >= 8
      && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47
      && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a;
    const isJpeg = bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
    if (!isPng && !isJpeg) {
      showStatus("Выберите корректный файл PNG или JPG");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      updateField('custom_logo', reader.result as string);
      updateField('logo_mode', 'custom');
    };
    reader.onerror = () => showStatus("Не удалось прочитать файл логотипа");
    reader.readAsDataURL(file);
  };

  return (
    <div className="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden min-h-0">
      {/* Form header with category tabs. */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-3 sm:px-4 py-2 sm:py-2.5 shrink-0 overflow-x-auto no-scrollbar">
        <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab('subject')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-bold transition-all shrink-0 ${
              activeTab === 'subject'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Предмет и кафедра</span>
            <span className="sm:hidden">Предмет</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('university')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-bold transition-all shrink-0 ${
              activeTab === 'university'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <School className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Вуз и ГОСТ</span>
            <span className="sm:hidden">Вуз</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('work')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-bold transition-all shrink-0 ${
              activeTab === 'work'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Реквизиты работы</span>
            <span className="sm:hidden">Работа</span>
          </button>
        </div>

        {statusMsg && (
          <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 animate-in fade-in shrink-0 ml-2">
            {statusMsg}
          </span>
        )}
      </div>

      {/* Form content. */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 text-xs text-slate-700 min-h-0">
        {/* Subject and department tab. */}
        {activeTab === 'subject' && (
          <div className="space-y-4 animate-in fade-in duration-100">
            <div className="flex flex-wrap items-center justify-between gap-2 bg-blue-50/60 border border-blue-100 rounded-xl p-3">
              <div>
                <span className="font-bold text-blue-950 text-xs block">Семестровый шаблон предмета</span>
                <p className="text-[11px] text-blue-800">
                  Настройки кафедры и преподавателя сохраняются для всех работ по этой дисциплине.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {activeSubjectId && onDeletePreset && subjectPresets.some(p => p.id === activeSubjectId) && (
                  <button
                    type="button"
                    onClick={() => onDeletePreset(activeSubjectId)}
                    className="shrink-0 flex items-center gap-1 bg-white hover:bg-red-50 text-red-600 border border-red-200 px-2.5 py-1.5 rounded-lg font-bold text-xs shadow-sm transition-all active:scale-95"
                    title="Удалить текущий шаблон дисциплины"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Удалить шаблон</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSaveCurrentAsPreset}
                  className="shrink-0 flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg font-bold text-xs shadow-sm transition-all active:scale-95"
                >
                  <Check className="h-3.5 w-3.5" />
                  <span>Сохранить в шаблон</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Название дисциплины (предмета):
                </label>
                <input
                  type="text"
                  value={meta.discipline}
                  onChange={e => updateField('discipline', e.target.value)}
                  placeholder="например, Физика"
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Факультет / Институт:
                </label>
                <input
                  type="text"
                  value={meta.institute}
                  onChange={e => updateField('institute', e.target.value)}
                  placeholder="например, Институт информационных технологий"
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Кафедра:
                </label>
                <input
                  type="text"
                  value={meta.department}
                  onChange={e => updateField('department', e.target.value)}
                  placeholder="например, Кафедра информационных систем"
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            {/* Teachers. */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <GraduationCap className="h-4 w-4 text-blue-600" />
                  Преподаватель (проверяющий):
                </span>
                <button
                  type="button"
                  onClick={handleAddTeacher}
                  className="flex items-center gap-1 text-[11px] font-bold text-blue-600 hover:text-blue-800 bg-blue-50 px-2 py-0.5 rounded transition-all active:scale-95"
                >
                  <Plus className="h-3 w-3" />
                  <span>Добавить</span>
                </button>
              </div>

              {(meta.teachers || []).map((t, idx) => {
                const isCustomRole = t.role !== '' && !(TEACHER_ROLES as readonly string[]).includes(t.role);
                return (
                <div key={idx} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    value={t.fio}
                    onChange={e => handleTeacherChange(idx, 'fio', e.target.value)}
                    placeholder="И.О. Фамилия (например: П.П. Петров)"
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={isCustomRole ? '__custom' : t.role}
                      onChange={e => {
                        if (e.target.value === '__custom') {
                          handleTeacherChange(idx, 'role', '');
                        } else {
                          handleTeacherChange(idx, 'role', e.target.value);
                        }
                      }}
                      className="flex-1 sm:w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 bg-white"
                      title="Должность проверяющего"
                    >
                      <option value="" disabled>Должность...</option>
                      {TEACHER_ROLES.map(r => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                      <option value="__custom">Другая (ввести вручную)...</option>
                    </select>
                    {isCustomRole && (
                      <input
                        type="text"
                        value={t.role}
                        onChange={e => handleTeacherChange(idx, 'role', e.target.value)}
                        placeholder="Своя должность"
                        className="flex-1 sm:w-32 rounded-lg border border-blue-300 px-2.5 py-1 text-xs text-slate-900 focus:outline-none focus:border-blue-500 bg-blue-50/40"
                      />
                    )}
                    {(meta.teachers || []).length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveTeacher(idx)}
                        className="p-1.5 text-slate-400 hover:text-red-600 rounded-md transition-colors shrink-0"
                        title="Удалить"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
                );
              })}
            </div>

            {/* Students and coauthors. */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-800 flex items-center gap-1.5">
                    <Users className="h-4 w-4 text-purple-600" />
                    Студенты (авторы / бригада):
                  </span>
                  <p className="text-[10.5px] text-slate-500">
                    Если работа выполняется бригадой, добавьте соавторов — титульный лист оформится по ГОСТ с подписями для каждого.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleAddStudent}
                  className="shrink-0 flex items-center gap-1 text-[11px] font-bold text-purple-600 hover:text-purple-800 bg-purple-50 px-2 py-1 rounded transition-all active:scale-95"
                >
                  <Plus className="h-3 w-3" />
                  <span>Добавить студента</span>
                </button>
              </div>

              {(meta.students || []).map((s, idx) => (
                <div key={idx} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    value={s.fio}
                    onChange={e => handleStudentChange(idx, 'fio', e.target.value)}
                    placeholder={idx === 0 ? "И.О. Фамилия автора (например: И.И. Иванов)" : `И.О. Фамилия соавтора #${idx + 1} (например: П.С. Сидоров)`}
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                  />
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={s.group}
                      onChange={e => handleStudentChange(idx, 'group', e.target.value)}
                      placeholder="Группа (например: ИВТ-101)"
                      className="flex-1 sm:w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                    />
                    {(meta.students || []).length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveStudent(idx)}
                        className="p-1.5 text-slate-400 hover:text-red-600 rounded-md transition-colors shrink-0"
                        title="Удалить студента"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Teacher-specific AI instructions. */}
            <div className="space-y-1.5 pt-2 border-t border-slate-100">
              <label className="block text-[11px] font-bold text-slate-800 flex items-center justify-between">
                <span>Индивидуальные указания преподавателя (для ИИ):</span>
                <span className="text-[10px] text-slate-400 font-normal">Передаются ИИ-агенту</span>
              </label>
              <textarea
                value={meta.custom_instructions || ''}
                onChange={e => updateField('custom_instructions', e.target.value)}
                placeholder="Специфические требования к этой дисциплине: например, «код только на Python 3.12», «схемы по ГОСТ 19», «в выводах указать время пинга»..."
                rows={3}
                className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800 focus:outline-none focus:border-blue-500 leading-relaxed resize-none"
              />
            </div>
          </div>
        )}

        {/* University and GOST tab. */}
        {activeTab === 'university' && (
          <div className="space-y-4 animate-in fade-in duration-100">
            <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 border border-slate-200 rounded-xl p-3">
              <div>
                <span className="font-bold text-slate-900 text-xs block">Глобальный профиль учебного заведения</span>
                <p className="text-[11px] text-slate-500">
                  Заполняется один раз и действует для всех предметов и отчётов.
                </p>
              </div>
              <button
                type="button"
                onClick={handleSaveGlobalProfile}
                className="shrink-0 flex items-center gap-1 bg-slate-800 hover:bg-slate-900 text-white px-3 py-1.5 rounded-lg font-bold text-xs shadow-sm transition-all active:scale-95"
              >
                <Check className="h-3.5 w-3.5" />
                <span>Сохранить в профиль</span>
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Полное наименование университета (для шапки титульника):
                </label>
                <textarea
                  value={meta.university}
                  onChange={e => updateField('university', e.target.value)}
                  rows={2}
                  placeholder="например: НАЦИОНАЛЬНЫЙ ИССЛЕДОВАТЕЛЬСКИЙ УНИВЕРСИТЕТ"
                  className="w-full rounded-lg border border-slate-300 p-2 text-xs text-slate-900 focus:outline-none focus:border-blue-500 leading-relaxed font-medium"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Город:
                  </label>
                  <input
                    type="text"
                    value={meta.city}
                    onChange={e => updateField('city', e.target.value)}
                    placeholder="например: Москва"
                    className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Оформление шапки (Логотип):
                  </label>
                  <select
                    value={normalizeLogoMode(meta.logo_mode)}
                    onChange={e => updateField('logo_mode', e.target.value as LogoMode)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium bg-white"
                  >
                    <option value="none">Без логотипа (стандарт ГОСТ 2.105)</option>
                    <option value="default">С логотипом СамГТУ (встроенный)</option>
                    <option value="custom">Свой логотип (загрузить файл)</option>
                  </select>
                  {normalizeLogoMode(meta.logo_mode) === 'custom' && (
                    <div className="mt-1.5 flex items-center gap-2">
                      {meta.custom_logo && (
                        <img src={meta.custom_logo} alt="Свой логотип" className="h-8 max-w-[80px] object-contain rounded border border-slate-200 bg-white px-1" />
                      )}
                      <label className="flex-1 cursor-pointer rounded-lg border border-dashed border-slate-300 bg-slate-50 px-2.5 py-1.5 text-[11px] text-slate-600 hover:border-blue-400 hover:text-slate-900 text-center transition-colors">
                        {meta.custom_logo ? 'Заменить файл (PNG/JPG до 2 МБ)' : 'Выбрать файл (PNG/JPG до 2 МБ)'}
                        <input
                          type="file"
                          accept="image/png,image/jpeg"
                          className="hidden"
                          onChange={e => { void handleCustomLogoFile(e.target.files?.[0]); }}
                        />
                      </label>
                      {meta.custom_logo && (
                        <button
                          type="button"
                          onClick={() => updateField('custom_logo', undefined)}
                          className="p-1.5 text-slate-400 hover:text-red-600 rounded-md transition-colors shrink-0"
                          title="Убрать свой логотип"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Министерство (ведомство):
                </label>
                <input
                  type="text"
                  value={meta.ministry || 'МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ'}
                  onChange={e => updateField('ministry', e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Default student. */}
              <div className="pt-2 border-t border-slate-100 space-y-2">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <Users className="h-4 w-4 text-purple-600" />
                  Основной студент (автор по умолчанию):
                </span>
                <p className="text-[10.5px] text-slate-500">
                  Сохраняется в глобальный профиль вуза. Состав бригады для текущей работы настраивается во вкладке «Предмет и кафедра».
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] text-slate-500 mb-0.5">И.О. Фамилия студента:</label>
                    <input
                      type="text"
                      value={meta.students[0]?.fio || ''}
                      onChange={e => handleStudentChange(0, 'fio', e.target.value)}
                      placeholder="И.И. Иванов"
                      className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 mb-0.5">Академическая группа:</label>
                    <input
                      type="text"
                      value={meta.students[0]?.group || ''}
                      onChange={e => handleStudentChange(0, 'group', e.target.value)}
                      placeholder="например: ИВТ-101"
                      className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Current work metadata tab. */}
        {activeTab === 'work' && (
          <div className="space-y-4 animate-in fade-in duration-100">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Вид работы:
                </label>
                <select
                  value={
                    [
                      "о выполнении лабораторной работы",
                      "о выполнении практической работы",
                      "по расчетно-графической работе",
                      "по курсовой работе",
                      "по курсовому проекту",
                      "по научно-исследовательской работе",
                      "по производственной практике",
                      "по учебной практике",
                      "по преддипломной практике",
                      "по контрольной работе"
                    ].includes(meta.work_type)
                      ? meta.work_type
                      : "custom"
                  }
                  onChange={e => {
                    if (e.target.value === "custom") {
                      updateField('work_type', meta.work_type && !meta.work_type.startsWith("о выполнении") ? meta.work_type : "по индивидуальному заданию");
                    } else {
                      updateField('work_type', e.target.value);
                    }
                  }}
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 bg-white font-medium"
                >
                  <option value="о выполнении лабораторной работы">Лабораторная работа</option>
                  <option value="о выполнении практической работы">Практическая работа</option>
                  <option value="по расчетно-графической работе">Расчетно-графическая работа (РГР)</option>
                  <option value="по курсовой работе">Курсовая работа</option>
                  <option value="по курсовому проекту">Курсовой проект</option>
                  <option value="по научно-исследовательской работе">Научно-исследовательская работа (НИР)</option>
                  <option value="по производственной практике">Производственная практика</option>
                  <option value="по учебной практике">Учебная практика</option>
                  <option value="по преддипломной практике">Преддипломная практика</option>
                  <option value="по контрольной работе">Контрольная работа</option>
                  <option value="custom">Другой вид работы (ввести вручную)...</option>
                </select>
                {![
                  "о выполнении лабораторной работы",
                  "о выполнении практической работы",
                  "по расчетно-графической работе",
                  "по курсовой работе",
                  "по курсовому проекту",
                  "по научно-исследовательской работе",
                  "по производственной практике",
                  "по учебной практике",
                  "по преддипломной практике",
                  "по контрольной работе"
                ].includes(meta.work_type) && (
                  <input
                    type="text"
                    value={meta.work_type}
                    onChange={e => updateField('work_type', e.target.value)}
                    placeholder="Например: по технологической практике"
                    className="mt-1.5 w-full rounded-lg border border-blue-300 px-2.5 py-1 text-xs text-slate-900 focus:outline-none focus:border-blue-500 bg-blue-50/40"
                  />
                )}
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Номер работы:
                </label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={meta.work_number}
                  onChange={e => updateField('work_number', parseInt(e.target.value) || 1)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-bold"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Год:
                </label>
                <input
                  type="number"
                  min={2020}
                  max={2035}
                  value={meta.year}
                  onChange={e => updateField('year', parseInt(e.target.value) || new Date().getFullYear())}
                  className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="sm:col-span-3">
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  Тема работы:
                </label>
                <textarea
                  value={meta.work_theme}
                  onChange={e => updateField('work_theme', e.target.value)}
                  rows={2}
                  placeholder="например, Исследование методов фильтрации сетевого трафика..."
                  className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500 leading-relaxed font-medium resize-none"
                />
              </div>
            </div>

            {/* Bibliography under GOST R 7.0.5. */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-800 flex items-center gap-1.5">
                    <BookOpen className="h-4 w-4 text-emerald-600" />
                    Список использованных источников:
                  </span>
                  <p className="text-[10.5px] text-slate-500">
                    Оформляется автоматически по ГОСТ Р 7.0.5 последним разделом документа.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleAddRef}
                  className="shrink-0 flex items-center gap-1 text-[11px] font-bold text-emerald-600 hover:text-emerald-800 bg-emerald-50 px-2 py-1 rounded transition-all active:scale-95"
                >
                  <Plus className="h-3 w-3" />
                  <span>Добавить источник</span>
                </button>
              </div>

              {(meta.references || []).map((ref, idx) => (
                <div key={ref.id || idx} className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5 space-y-2">
                  <div className="flex items-center gap-2">
                    <select
                      value={['book', 'article', 'website', 'standard'].includes(ref.kind) ? ref.kind : 'book'}
                      onChange={e => handleRefChange(idx, 'kind', e.target.value)}
                      className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-900 focus:outline-none focus:border-blue-500 bg-white font-bold"
                      title="Тип источника"
                    >
                      {REFERENCE_KINDS.map(k => (
                        <option key={k.value} value={k.value}>{k.label}</option>
                      ))}
                    </select>
                    <span className="text-[11px] font-bold text-slate-400">№{idx + 1}</span>
                    <div className="flex-1" />
                    <button
                      type="button"
                      onClick={() => handleRemoveRef(idx)}
                      className="p-1.5 text-slate-400 hover:text-red-600 rounded-md transition-colors shrink-0"
                      title="Удалить источник"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {ref.kind !== 'standard' && (
                      <input
                        type="text"
                        value={ref.authors}
                        onChange={e => handleRefChange(idx, 'authors', e.target.value)}
                        placeholder="И.О. Фамилия автора"
                        className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                      />
                    )}
                    <input
                      type="text"
                      value={ref.title}
                      onChange={e => handleRefChange(idx, 'title', e.target.value)}
                      placeholder={ref.kind === 'website' ? 'Название страницы' : ref.kind === 'standard' ? 'Обозначение и название (например: ГОСТ 7.32-2017)' : 'Название (например: Основы сетей)'}
                      className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                    />
                    {ref.kind !== 'website' && (
                      <>
                        <input
                          type="text"
                          value={ref.place}
                          onChange={e => handleRefChange(idx, 'place', e.target.value)}
                          placeholder="Место (например: М.)"
                          className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                        />
                        <input
                          type="text"
                          value={ref.publisher}
                          onChange={e => handleRefChange(idx, 'publisher', e.target.value)}
                          placeholder={ref.kind === 'article' ? 'Журнал (например: Сети и связь)' : 'Издательство (например: Техника)'}
                          className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                        />
                      </>
                    )}
                    <input
                      type="text"
                      value={ref.year}
                      onChange={e => handleRefChange(idx, 'year', e.target.value)}
                      placeholder="Год (например: 2024)"
                      className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                    />
                    <input
                      type="text"
                      value={ref.details}
                      onChange={e => handleRefChange(idx, 'details', e.target.value)}
                      placeholder={ref.kind === 'article' ? 'Детали (например: № 3. – С. 12–18)' : ref.kind === 'website' ? 'Дата обращения (например: 24.09.2026)' : 'Детали (например: 256 с.)'}
                      className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                    />
                    {ref.kind === 'website' && (
                      <input
                        type="text"
                        value={ref.url}
                        onChange={e => handleRefChange(idx, 'url', e.target.value)}
                        placeholder="URL (например: https://...)"
                        className="sm:col-span-2 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-500"
                      />
                    )}
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed bg-white rounded-lg border border-slate-200 px-2.5 py-1.5">
                    {idx + 1}.{'\u00A0'}{formatReference(ref)}
                  </p>
                </div>
              ))}
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-[11px] text-slate-500 leading-relaxed">
              <strong>Подсказка:</strong> Настройки выравнивания заголовков, нумерации страниц и формул LaTeX настраиваются на верхней панели прямо над листом А4.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
