"""Convert inline and display LaTeX equations to native Word OMML elements."""

import re
import html
from typing import Optional
from docx.oxml import parse_xml

try:
    import latex2mathml.converter
    import mathml2omml
    HAS_MATH_CONVERTERS = True
except ImportError:
    HAS_MATH_CONVERTERS = False

MATH_SYMBOLS = {
    r'\to': '→',
    r'\rightarrow': '→',
    r'\leftarrow': '←',
    r'\leftrightarrow': '↔',
    r'\Rightarrow': '⇒',
    r'\Leftarrow': '⇐',
    r'\approx': '≈',
    r'\le': '≤',
    r'\leq': '≤',
    r'\ge': '≥',
    r'\geq': '≥',
    r'\neq': '≠',
    r'\pm': '±',
    r'\mp': '∓',
    r'\times': '×',
    r'\cdot': '·',
    r'\div': '÷',
    r'\infty': '∞',
    r'\partial': '∂',
    r'\nabla': '∇',
    r'\alpha': 'α',
    r'\beta': 'β',
    r'\gamma': 'γ',
    r'\delta': 'δ',
    r'\epsilon': 'ε',
    r'\theta': 'θ',
    r'\lambda': 'λ',
    r'\mu': 'μ',
    r'\pi': 'π',
    r'\rho': 'ρ',
    r'\sigma': 'σ',
    r'\tau': 'τ',
    r'\phi': 'φ',
    r'\omega': 'ω',
    r'\Delta': 'Δ',
    r'\Gamma': 'Γ',
    r'\Lambda': 'Λ',
    r'\Sigma': 'Σ',
    r'\Omega': 'Ω',
    r'\forall': '∀',
    r'\exists': '∃',
    r'\in': '∈',
    r'\notin': '∉',
    r'\subset': '⊂',
    r'\subseteq': '⊆',
    r'\cup': '∪',
    r'\cap': '∩',
    r'\emptyset': '∅',
    # Preserve operators and common functions before the catch-all strips commands.
    r'\sum': '∑',
    r'\prod': '∏',
    r'\coprod': '∐',
    r'\int': '∫',
    r'\iint': '∬',
    r'\iiint': '∭',
    r'\oint': '∮',
    r'\log': 'log',
    r'\ln': 'ln',
    r'\lg': 'lg',
    r'\lim': 'lim',
    r'\exp': 'exp',
    r'\sin': 'sin',
    r'\cos': 'cos',
    r'\tan': 'tan',
    r'\cot': 'cot',
    r'\sec': 'sec',
    r'\csc': 'csc',
    r'\arcsin': 'arcsin',
    r'\arccos': 'arccos',
    r'\arctan': 'arctan',
    r'\sinh': 'sinh',
    r'\cosh': 'cosh',
    r'\tanh': 'tanh',
    r'\min': 'min',
    r'\max': 'max',
    r'\sup': 'sup',
    r'\inf': 'inf',
    r'\arg': 'arg',
    r'\deg': 'deg',
    r'\dim': 'dim',
    r'\det': 'det',
    r'\gcd': 'gcd',
    r'\hom': 'hom',
    r'\ker': 'ker',
    r'\degree': '°',
    r'\circ': '°',
}

SUPERSCRIPTS = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
SUBSCRIPTS = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")


def fallback_latex_to_unicode(latex_str: str) -> str:
    """Convert basic LaTeX constructs to readable Unicode text."""
    res = latex_str.strip()
    for cmd, sym in MATH_SYMBOLS.items():
        res = re.sub(re.escape(cmd) + r'(?![a-zA-Z])', sym, res)
    
    # \frac{a}{b} -> a/b
    res = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'(\1)/(\2)', res)
    # \sqrt{x} -> √(x)
    res = re.sub(r'\\sqrt\{([^{}]+)\}', r'√(\1)', res)
    # \text{...}, \mathrm{...}, \mathbf{...}
    res = re.sub(r'\\(?:text|mathrm|mathbf|operatorname|mathit)\{([^{}]+)\}', r'\1', res)
    # 2^8 -> 2⁸
    res = re.sub(r'\^\{?([0-9\+\-\=\(\)ni]+)\}?', lambda m: m.group(1).translate(SUPERSCRIPTS), res)
    # x_1 -> x₁
    res = re.sub(r'_\{?([0-9\+\-\=\(\)aehijklmnoprstuvx]+)\}?', lambda m: m.group(1).translate(SUBSCRIPTS), res)
    # Strip remaining command backslashes.
    res = re.sub(r'\\[a-zA-Z]+', '', res)
    # Strip grouping braces.
    res = res.replace('{', '').replace('}', '')
    return res


def latex_to_omml(latex_code: str, is_block: bool = False):
    """Convert a LaTeX string to an lxml OMML element (m:oMath)."""
    clean_latex = latex_code.strip()
    if not clean_latex:
        return None

    # Normalize common variants only at command boundaries to preserve
    # unrelated commands such as \stock and \atom.
    clean_latex = re.sub(r'\\to(?![a-zA-Z])', r'\\rightarrow', clean_latex)

    if HAS_MATH_CONVERTERS:
        try:
            mathml = latex2mathml.converter.convert(clean_latex)
            omml_str = mathml2omml.convert(mathml)
            if 'xmlns:m=' not in omml_str:
                omml_str = omml_str.replace(
                    '<m:oMath',
                    '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
                )
            if is_block:
                omml_block = f'<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">{omml_str}</m:oMathPara>'
                return parse_xml(omml_block)
            return parse_xml(omml_str)
        except Exception:
            pass

    # Fall back to Unicode OMML using the project-required Times New Roman font.
    unicode_text = fallback_latex_to_unicode(clean_latex)
    safe_text = html.escape(unicode_text)
    omml_fallback = f'''<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <m:r>
        <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr>
        <m:t>{safe_text}</m:t>
      </m:r>
    </m:oMath>'''
    if is_block:
        omml_fallback = f'<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">{omml_fallback}</m:oMathPara>'
    return parse_xml(omml_fallback)
