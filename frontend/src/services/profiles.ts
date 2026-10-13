import type { GlobalUniversityProfile, SubjectPreset, ReportMetadata, LogoMode } from '../types/index.ts';

export type { GlobalUniversityProfile, SubjectPreset };
export type { LogoMode };

export const PROFILE_FORMAT = 'report-engine-profile' as const;
export const PROFILE_VERSION = 1 as const;
export const PROFILE_MAX_BYTES = 4 * 1024 * 1024;

export type ProfileMetadata = Pick<ReportMetadata,
  | 'university'
  | 'ministry'
  | 'logo_mode'
  | 'custom_logo'
  | 'city'
  | 'institute'
  | 'department'
  | 'doc_type'
  | 'work_type'
  | 'work_number'
  | 'discipline'
  | 'students'
  | 'teachers'
  | 'year'
>;

export interface ReportEngineProfile {
  format: typeof PROFILE_FORMAT;
  version: typeof PROFILE_VERSION;
  subject: SubjectPreset;
  meta: ProfileMetadata;
}

const GLOBAL_PROFILE_KEY = 'global_profile';
const SUBJECT_PRESETS_KEY = 'subject_presets';
const ACTIVE_SUBJECT_ID_KEY = 'active_subject_id';

export const normalizeLogoMode = (value: unknown): LogoMode => {
  if (value === 'default' || value === 'custom' || value === 'none') return value;
  return 'none';
};

export const DEFAULT_GLOBAL_PROFILE: GlobalUniversityProfile = {
  university: "",
  ministry: "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ",
  city: "",
  logo_mode: "none",
  default_student: {
    fio: "",
    group: ""
  }
};

export const DEFAULT_SUBJECT_PRESETS: SubjectPreset[] = [];

export const getGlobalProfile = (): GlobalUniversityProfile => {
  try {
    const raw = localStorage.getItem(GLOBAL_PROFILE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        ...DEFAULT_GLOBAL_PROFILE,
        ...parsed,
        logo_mode: normalizeLogoMode(parsed.logo_mode),
        default_student: parsed.default_student || DEFAULT_GLOBAL_PROFILE.default_student
      };
    }
  } catch {}
  return DEFAULT_GLOBAL_PROFILE;
};

export const saveGlobalProfile = (profile: GlobalUniversityProfile): void => {
  try {
    localStorage.setItem(GLOBAL_PROFILE_KEY, JSON.stringify(profile));
  } catch (e) {
    console.warn("Failed to save global profile:", e);
  }
};

export const getSubjectPresets = (): SubjectPreset[] => {
  try {
    const raw = localStorage.getItem(SUBJECT_PRESETS_KEY);
    if (raw !== null) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    }
  } catch {}
  return [];
};

export const saveSubjectPresets = (presets: SubjectPreset[]): void => {
  try {
    localStorage.setItem(SUBJECT_PRESETS_KEY, JSON.stringify(presets));
  } catch (e) {
    console.warn("Failed to save subject presets:", e);
  }
};

export const deleteSubjectPreset = (id: string): SubjectPreset[] => {
  const current = getSubjectPresets();
  const updated = current.filter(p => p.id !== id);
  saveSubjectPresets(updated);
  return updated;
};

export const getActiveSubjectId = (): string => {
  try {
    const saved = localStorage.getItem(ACTIVE_SUBJECT_ID_KEY);
    if (saved) {
      return saved;
    }
  } catch {}
  const presets = getSubjectPresets();
  return presets[0]?.id || "";
};

export const setActiveSubjectId = (id: string): void => {
  try {
    localStorage.setItem(ACTIVE_SUBJECT_ID_KEY, id);
  } catch {}
};

export const createNewSubjectPreset = (name = "Новая дисциплина"): SubjectPreset => {
  return {
    id: `subj_${Date.now()}`,
    name,
    institute: "",
    department: "",
    teachers: [{ fio: "", role: "ст. преп." }],
    custom_instructions: ""
  };
};

const PROFILE_META_FIELDS: (keyof ProfileMetadata)[] = [
  'university', 'ministry', 'logo_mode', 'custom_logo', 'city', 'institute',
  'department', 'doc_type', 'work_type', 'work_number', 'discipline',
  'students', 'teachers', 'year',
];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const profileError = (message: string): Error => new Error(`Профиль повреждён: ${message}`);

const validatePeople = (value: unknown, kind: 'students' | 'teachers'): boolean => {
  if (!Array.isArray(value) || value.length === 0) return false;
  return value.every(item => {
    if (!isRecord(item) || typeof item.fio !== 'string') return false;
    return kind === 'students' ? typeof item.group === 'string' : typeof item.role === 'string';
  });
};

const validateSubject = (value: unknown): value is SubjectPreset => {
  if (!isRecord(value)
    || !Object.keys(value).every(key => ['id', 'name', 'institute', 'department', 'teachers', 'custom_instructions', 'last_work_number'].includes(key))
    || typeof value.id !== 'string'
    || typeof value.name !== 'string'
    || typeof value.institute !== 'string'
    || typeof value.department !== 'string'
    || !validatePeople(value.teachers, 'teachers')) {
    return false;
  }
  if (value.custom_instructions !== undefined && typeof value.custom_instructions !== 'string') return false;
  return value.last_work_number === undefined
    || (Number.isInteger(value.last_work_number) && (value.last_work_number as number) > 0);
};

const validateProfileMetadata = (value: unknown): value is ProfileMetadata => {
  if (!isRecord(value)) return false;
  if (!Object.keys(value).every(key => PROFILE_META_FIELDS.includes(key as keyof ProfileMetadata))) return false;
  const requiredStrings = ['university', 'ministry', 'city', 'institute', 'department', 'doc_type', 'work_type', 'discipline'];
  if (!requiredStrings.every(key => typeof value[key] === 'string')) return false;
  if (!Number.isInteger(value.work_number) || (value.work_number as number) < 0) return false;
  if (!Number.isInteger(value.year)) return false;
  if (!validatePeople(value.students, 'students') || !validatePeople(value.teachers, 'teachers')) return false;
  if (value.logo_mode !== 'default' && value.logo_mode !== 'custom' && value.logo_mode !== 'none') return false;
  if (value.custom_logo !== undefined && value.custom_logo !== null && typeof value.custom_logo !== 'string') return false;
  if (value.logo_mode === 'custom' && typeof value.custom_logo !== 'string') return false;
  return PROFILE_META_FIELDS.every(key => value[key] !== undefined || key === 'custom_logo');
};

/** Build the versioned portable profile from the existing subject and metadata models. */
export const createProfile = (subject: SubjectPreset, meta: ReportMetadata): ReportEngineProfile => ({
  format: PROFILE_FORMAT,
  version: PROFILE_VERSION,
  subject: { ...subject, teachers: subject.teachers.map(teacher => ({ ...teacher })) },
  meta: Object.fromEntries(PROFILE_META_FIELDS
    .filter(field => meta[field] !== undefined)
    .map(field => [field, meta[field]])) as ProfileMetadata,
});

/** Validate an imported profile and return its typed, versioned representation. */
export const parseProfile = (value: unknown): ReportEngineProfile => {
  if (!isRecord(value) || value.format !== PROFILE_FORMAT) {
    throw new Error('Неверный формат файла профиля. Ожидается report-engine-profile.');
  }
  if (value.version !== PROFILE_VERSION) {
    throw new Error(`Неподдерживаемая версия профиля: ${String(value.version)}. Ожидается версия ${PROFILE_VERSION}.`);
  }
  if (!validateSubject(value.subject)) throw profileError('некорректный шаблон дисциплины');
  if (!validateProfileMetadata(value.meta)) throw profileError('некорректные реквизиты титульного листа');
  return {
    format: PROFILE_FORMAT,
    version: PROFILE_VERSION,
    subject: value.subject,
    meta: value.meta,
  };
};

export const serializeProfile = (profile: ReportEngineProfile): string =>
  JSON.stringify(parseProfile(profile), null, 2);

/** Apply a profile to the current report without changing report-specific fields. */
export const applyProfile = (profile: ReportEngineProfile, current: ReportMetadata): ReportMetadata => ({
  ...current,
  ...profile.meta,
  discipline: profile.subject.name,
  institute: profile.subject.institute,
  department: profile.subject.department,
  teachers: profile.subject.teachers.map(teacher => ({ ...teacher })),
  custom_instructions: profile.subject.custom_instructions || '',
});

export const profileFilename = (discipline: string): string => {
  const transliteration: Record<string, string> = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'j',
    к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f',
    х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'shh', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
  };
  const slug = discipline.trim().toLowerCase().split('').map(char => transliteration[char] ?? char)
    .join('').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  return `profile-${slug || 'discipline'}.json`;
};

/**
 * Assemble ReportMetadata from global, subject, and work-session settings.
 * Global settings own institutional details and the default student; subject
 * settings own department, teachers, and instructions; work settings own the
 * current number, theme, work type, and layout.
 */
export const buildReportMetadata = (
  global: GlobalUniversityProfile,
  subject: SubjectPreset | undefined,
  workSession: Partial<ReportMetadata>
): ReportMetadata => {
  return {
    university: global.university || "",
    ministry: global.ministry || "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ",
    logo_mode: normalizeLogoMode(global.logo_mode),
    custom_logo: global.custom_logo,
    city: global.city || "",
    institute: subject?.institute || "",
    department: subject?.department || "",
    discipline: subject?.name || "",
    teachers: subject?.teachers && subject.teachers.length > 0 
      ? subject.teachers 
      : [{ fio: "", role: "ст. преп." }],
    custom_instructions: subject?.custom_instructions || "",
    students: workSession.students && workSession.students.length > 0
      ? workSession.students
      : (global.default_student?.fio ? [global.default_student] : [{ fio: "", group: "" }]),
    doc_type: workSession.doc_type || "ОТЧЕТ",
    work_type: workSession.work_type || "о выполнении лабораторной работы",
    work_number: workSession.work_number ?? 1,
    work_theme: workSession.work_theme || "",
    year: workSession.year || new Date().getFullYear(),
    heading_alignment: workSession.heading_alignment || "center",
    page_numbering: workSession.page_numbering || "center",
    page_break_before_h1: workSession.page_break_before_h1 ?? false,
    hide_captions: workSession.hide_captions ?? false,
    prompt_latex: workSession.prompt_latex ?? true,
    latex_mode: workSession.latex_mode || "omml",
  };
};
