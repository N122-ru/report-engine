export type LogoMode = 'default' | 'custom' | 'none';

export type ReferenceKind = 'book' | 'article' | 'website' | 'standard';

export const REFERENCE_KINDS: { value: ReferenceKind; label: string }[] = [
  { value: 'book', label: 'Книга' },
  { value: 'article', label: 'Статья' },
  { value: 'website', label: 'Сайт' },
  { value: 'standard', label: 'Стандарт' },
];

export interface ReferenceItem {
  id?: string;
  kind: ReferenceKind;
  authors: string;
  title: string;
  place: string;
  publisher: string;
  year: string;
  details: string;
  url: string;
}

export const emptyReference = (kind: ReferenceKind = 'book'): ReferenceItem => ({
  id: `ref_${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`,
  kind, authors: '', title: '', place: '', publisher: '', year: '', details: '', url: ''
});

export interface StudentInfo {
  fio: string;
  group: string;
}

export interface TeacherInfo {
  fio: string;
  role: string;
}

export const TEACHER_ROLES = [
  'доцент',
  'ст. преп.',
  'ассистент',
  'профессор',
  'зав. кафедрой',
  'преподаватель',
  'преп.',
] as const;

export interface ImageLayout {
  width_percent?: number;
  max_height_mm?: number;
  align?: 'center' | 'left' | 'right';
  keep_caption_with_image?: boolean;
  page_break_before?: boolean;
}

export interface ReportMetadata {
  university: string;
  ministry?: string;
  logo_mode?: LogoMode;
  custom_logo?: string;
  institute: string;
  department: string;
  doc_type: string;
  work_type: string;
  work_number: number;
  work_theme: string;
  discipline: string;
  students: StudentInfo[];
  teachers: TeacherInfo[];
  references?: ReferenceItem[];
  city: string;
  year: number;
  heading_alignment?: 'left' | 'center';
  page_numbering?: 'center' | 'right' | 'none';
  page_break_before_h1?: boolean;
  hide_captions?: boolean;
  image_layouts?: Record<string, ImageLayout>;
  custom_instructions?: string;
  prompt_latex?: boolean;
  prompt_code_blocks?: boolean;
  latex_mode?: 'omml' | 'unicode';
}

export interface GlobalUniversityProfile {
  university: string;
  ministry: string;
  city: string;
  logo_mode: LogoMode;
  custom_logo?: string;
  default_student: StudentInfo;
}

export interface SubjectPreset {
  id: string;
  name: string;
  institute: string;
  department: string;
  teachers: TeacherInfo[];
  custom_instructions?: string;
  last_work_number?: number;
}

export interface GenerateOptions {
  include_title_page: boolean;
  page_break_before_h1: boolean;
  heading_alignment?: 'left' | 'center';
  page_numbering?: 'center' | 'right' | 'none';
  hide_captions?: boolean;
  latex_mode?: 'omml' | 'unicode';
}

export interface LinterIssue {
  type: string;
  severity: 'ERROR' | 'WARNING' | 'INFO';
  message: string;
  location: string;
  fix_suggestion?: string;
}

export interface LinterMetrics {
  margins_mm: {
    left: number;
    right: number;
    top: number;
    bottom: number;
  };
  page_count_estimate: number;
  figures_count: number;
  tables_count: number;
  listings_count: number;
  empty_paragraphs_count: number;
}

export interface LinterResult {
  is_valid: boolean;
  score: number;
  errors: LinterIssue[];
  warnings: LinterIssue[];
  metrics: LinterMetrics;
}
