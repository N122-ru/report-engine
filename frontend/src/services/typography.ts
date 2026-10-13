/**
 * Mirror backend/app/engine/typography.py: apply_typography_rules.
 * Keep rule changes identical in both implementations.
 * JS word boundaries exclude Cyrillic, unlike Python re, so use the explicit
 * Unicode character class W. Verify byte-for-byte parity (AGENTS.md 2.22).
 */

export const NBSP = '\u00A0';
export const NB_HYPHEN = '\u2011';

// Match Unicode word characters as Python's re does.
const W = 'а-яёА-ЯЁa-zA-Z0-9_';
const NOT_W_BEFORE = `(?<=^|[^${W}])`;
const NOT_W_AFTER = `(?![${W}])`;

export function applyTypographyRules(input: string): string {
  if (!input) return input;
  let text = input;

  // Use NBSP plus em dash between words; preserve arithmetic minus signs.
  text = text.replace(/(\S)\s+[-–—]\s+(\S)/g, (m, left: string, right: string) => {
    if (/\d$/.test(left) && /^\d/.test(right)) return m;
    return `${left}${NBSP}— ${right}`;
  });

  // Bind prepositions and conjunctions to the following word.
  text = text.replace(
    new RegExp(`${NOT_W_BEFORE}([вВ]|[нН]а|[сС]|[пП]о|[кК]|[уУ]|[оО]|[иИ]з|[зЗ]а|[оО]т|[иИ]|[аА]|[нН]о|[дД]о|[пП]од|[пП]ри|[бБ]ез|[сС]о|[кК]о|[вВ]о|[оО]б|[оО]бо|[дД]ля|[нН]ад|[пП]ро|[мМ]еж)\\s+`, 'g'),
    `$1${NBSP}`
  );

  // Bind initials and surnames.
  text = text.replace(new RegExp(`${NOT_W_BEFORE}([А-ЯЁ]\\.\\s*[А-ЯЁ]\\.)\\s+([А-ЯЁ][а-яё-]+)`, 'g'), `$1${NBSP}$2`);
  text = text.replace(new RegExp(`${NOT_W_BEFORE}([А-ЯЁ][а-яё-]+)\\s+([А-ЯЁ]\\.\\s*[А-ЯЁ]\\.)`, 'g'), `$1${NBSP}$2`);

  // Bind reference labels to numbers.
  text = text.replace(
    new RegExp(`${NOT_W_BEFORE}(рисун(?:ок|ка|ку|ком|ке|ки|ках)|рис\\.|таблиц(?:а|ы|е|у|ей|ам|ах)|табл\\.|листинг(?:а|у|ом|е|и)?|вариант(?:а|у|ом|е)?|групп(?:а|ы|е|у|ой)?|стр\\.|с\\.)\\s+(\\d+)`, 'gi'),
    `$1${NBSP}$2`
  );
  // Bind the numero sign to its number.
  text = text.replace(new RegExp(`${NOT_W_BEFORE}(№)\\s*(\\d+)`, 'g'), `$1${NBSP}$2`);

  // Bind numbers to measurement units and year suffixes.
  text = text.replace(
    new RegExp(`(\\d+)\\s+(мм|см|м|км|мс|с|мин|ч|байт|КБ|МБ|ГБ|бит|кбит|Мбит|Гбит|Гц|кГц|МГц|ГГц|В|А|Вт|кВт|pt|dxa|г\\.|года)${NOT_W_AFTER}`, 'g'),
    `$1${NBSP}$2`
  );

  // Convert paired straight quotation marks to guillemets.
  text = text.replace(/[“„]([^”„\n]+?)[”"]/g, '«$1»');
  text = text.replace(/(?<!\d)"([^"\n]+?)"/g, '«$1»');

  // Keep technical hyphenated terms together with nonbreaking hyphens.
  text = text.replace(/\b[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5}\b/g, m => m.replace(/-/g, NB_HYPHEN));
  text = text.replace(/\b[01]{8}(?:-[01]{8})+\b/g, m => m.replace(/-/g, NB_HYPHEN));
  text = text.replace(
    new RegExp(`${NOT_W_BEFORE}(MAC|IPv4|IPv6|IP|Wi|TCP|UDP|DHCP|DNS|USB|Web|LAN|VLAN)-([а-яёА-ЯЁa-zA-Z0-9]+)${NOT_W_AFTER}`, 'g'),
    `$1${NB_HYPHEN}$2`
  );
  text = text.replace(new RegExp(`${NOT_W_BEFORE}Wi-Fi${NOT_W_AFTER}`, 'g'), `Wi${NB_HYPHEN}Fi`);

  return text;
}
