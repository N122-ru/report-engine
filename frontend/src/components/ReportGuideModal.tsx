import React, { useEffect, useRef } from 'react';
import { BookOpen, UploadCloud, X } from 'lucide-react';

interface ReportGuideModalProps {
  onClose: () => void;
  onVerify: () => void;
}

const sections = [
  { id: 'guide-start', label: 'С чего начать' },
  { id: 'guide-layout', label: 'Оформление' },
  { id: 'guide-structure', label: 'Структура' },
  { id: 'guide-materials', label: 'Рисунки и данные' },
  { id: 'guide-final', label: 'Перед сдачей' },
  { id: 'guide-faq', label: 'Частые вопросы' },
];

export const ReportGuideModal: React.FC<ReportGuideModalProps> = ({ onClose, onVerify }) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const skipFocusRestore = useRef(false);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.showModal();
    titleRef.current?.focus();
    return () => {
      if (dialog?.open) dialog.close();
      if (!skipFocusRestore.current && opener?.isConnected) opener.focus();
    };
  }, []);

  const goTo = (id: string) => {
    const heading = document.getElementById(id);
    heading?.scrollIntoView({ block: 'start' });
    heading?.focus({ preventScroll: true });
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="report-guide-title"
      aria-describedby="report-guide-intro"
      onCancel={event => { event.preventDefault(); onClose(); }}
      onMouseDown={event => {
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
      }}
      className="m-auto w-[calc(100vw_-_1rem)] max-w-4xl max-h-[92dvh] overflow-hidden rounded-2xl border border-slate-200 bg-white p-0 shadow-2xl backdrop:bg-slate-900/60"
    >
      <div
        className="flex max-h-[92dvh] flex-col overflow-hidden"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 sm:px-7 sm:py-5">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-blue-700">
              <BookOpen className="h-4 w-4" aria-hidden="true" />
              Самостоятельная сборка
            </div>
            <h2 id="report-guide-title" ref={titleRef} tabIndex={-1} className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
              Шпаргалка по отчёту
            </h2>
            <p id="report-guide-intro" className="mt-1 max-w-2xl text-sm text-slate-600">
              От исходных данных до готового .DOCX. Ориентиры взяты из шаблона и проверок конструктора.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть шпаргалку" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div className="min-h-0 overflow-y-auto overscroll-contain">
          <div className="grid gap-6 px-5 py-6 sm:px-7 md:grid-cols-[170px_minmax(0,1fr)] md:gap-9">
            <nav aria-label="Разделы шпаргалки" className="hidden self-start md:sticky md:top-6 md:block">
              <p className="mb-2 text-xs font-semibold text-slate-500">Быстрый переход</p>
              <ul className="space-y-0.5">
                {sections.map(section => (
                  <li key={section.id}>
                    <button type="button" onClick={() => goTo(section.id)} className="w-full rounded-md px-2 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
                      {section.label}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            <div className="min-w-0 space-y-7 text-sm leading-relaxed text-slate-700">
              <section aria-labelledby="guide-start">
                <h3 id="guide-start" tabIndex={-1} className="text-base font-bold text-slate-900">1. С чего начать</h3>
                <p className="mt-2">Возьмите за основу задание и методичку: уточните вид работы, тему, номер и требования преподавателя. Сверьте каждое число, команду, скриншот и результат с исходными материалами. Если факта нет, не придумывайте его.</p>
              </section>

              <section aria-labelledby="guide-layout">
                <h3 id="guide-layout" tabIndex={-1} className="text-base font-bold text-slate-900">2. Настройте документ</h3>
                <div className="mt-3 border-y border-slate-200 py-3 sm:grid sm:grid-cols-2 sm:gap-4">
                  <p><strong className="text-slate-900">Страница:</strong> A4; поля слева 30 мм, справа 15 мм, сверху и снизу по 20 мм.</p>
                  <p className="mt-2 sm:mt-0"><strong className="text-slate-900">Основной текст:</strong> Times New Roman 14 пт, интервал 1,5, красная строка 1,25 см, выравнивание по ширине.</p>
                </div>
                <p className="mt-3">На титульном листе укажите вуз, дисциплину, вид и тему работы, автора и проверяющего в формате «И.О. Фамилия», группу, город и год. В шаблоне конструктора титульный лист без номера; далее номер страницы ставится внизу по центру.</p>
                <p className="mt-2 text-xs text-slate-500">Это настройки шаблона по умолчанию. Если ваша методичка требует иного, следуйте ей.</p>
              </section>

              <section aria-labelledby="guide-structure">
                <h3 id="guide-structure" tabIndex={-1} className="text-base font-bold text-slate-900">3. Соберите содержание</h3>
                <ol className="mt-3 list-decimal space-y-3 border-l-2 border-blue-200 pl-7 marker:font-semibold marker:text-blue-700">
                  <li><strong className="text-slate-900">Цель работы.</strong> В 1–2 предложениях назовите объект и задачу работы.</li>
                  <li><strong className="text-slate-900">Ход работы.</strong> Опишите действия по порядку, нумерованным списком и связным текстом. После действия покажите подтверждающий результат: измерение, расчёт или рисунок.</li>
                  <li><strong className="text-slate-900">Вывод.</strong> В 1–2 предложениях свяжите полученный результат с целью. Пишите только то, что подтверждено данными работы.</li>
                </ol>
                <p className="mt-3 rounded-lg bg-slate-50 px-4 py-3 text-slate-700"><strong className="text-slate-900">Манера письма:</strong> «настроено», «рассчитано», «получено». Кратко объясняйте назначение элемента именно в вашей работе; избегайте «я сделал», общей теории и канцелярита.</p>
              </section>

              <section aria-labelledby="guide-materials">
                <h3 id="guide-materials" tabIndex={-1} className="text-base font-bold text-slate-900">4. Покажите доказательства</h3>
                <ul className="mt-3 list-disc space-y-2 pl-5 marker:text-slate-400">
                  <li><strong className="text-slate-900">Рисунки:</strong> сначала содержательная ссылка в тексте («…показано на рисунке 2»), затем Markdown-ссылка с названием в alt-тексте, начиная его с заглавной буквы. Система сама сформирует подпись «Рисунок 2 — Название» без точки; отдельную строку с этой подписью не добавляйте.</li>
                  <li><strong className="text-slate-900">Таблицы:</strong> используйте для сводных числовых данных, подпись «Таблица 1 — Название» размещайте над таблицей. Ход работы таблицей не оформляйте.</li>
                  <li><strong className="text-slate-900">Формулы:</strong> сложный расчёт ставьте отдельной строкой, пояснение символов начинайте с «где» на следующей строке. Не прячьте формулы в таблицы или блоки кода.</li>
                  <li><strong className="text-slate-900">Источники:</strong> если пользовались литературой, добавьте список источников и ссылки в тексте в квадратных скобках, например [1].</li>
                </ul>
              </section>

              <section aria-labelledby="guide-final">
                <h3 id="guide-final" tabIndex={-1} className="text-base font-bold text-slate-900">5. Проверьте перед сдачей</h3>
                <ul className="mt-3 list-disc space-y-1.5 pl-5 marker:text-slate-400">
                  <li>Цель, ход и вывод на месте; тема и номер совпадают с заданием.</li>
                  <li>Каждый рисунок действительно вставлен, упомянут в тексте и имеет уникальный номер.</li>
                  <li>Нет пустых строк для подгонки страниц, точек в конце заголовков и подписей, служебных путей и неподтверждённых чисел.</li>
                  <li>Проверьте собственный .DOCX нормоконтролем, затем откройте готовый файл и просмотрите реальную вёрстку.</li>
                </ul>
              </section>

              <section aria-labelledby="guide-faq">
                <h3 id="guide-faq" tabIndex={-1} className="text-base font-bold text-slate-900">Частые вопросы</h3>
                <div className="mt-3 divide-y divide-slate-200 border-y border-slate-200">
                  <details className="group py-3">
                    <summary className="cursor-pointer font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">Методичка требует другой структуры или нумерации?</summary>
                    <p className="mt-2 text-slate-600">Ориентируйтесь на требования преподавателя. Три раздела и параметры страницы здесь описывают базовый шаблон конструктора, а не любой учебный документ.</p>
                  </details>
                  <details className="group py-3">
                    <summary className="cursor-pointer font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">Что делать, если нет скриншота или значения?</summary>
                    <p className="mt-2 text-slate-600">Вернитесь к исходным данным или выполните проверку заново. Не подменяйте отсутствующий результат вымышленным числом либо изображением.</p>
                  </details>
                  <details className="group py-3">
                    <summary className="cursor-pointer font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">Можно ли сдавать сразу после автоматической проверки?</summary>
                    <p className="mt-2 text-slate-600">Проверка находит формальные ошибки и предупреждения, но не заменяет сверку с заданием и просмотр готового DOCX/PDF.</p>
                  </details>
                </div>
              </section>
            </div>
          </div>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3 sm:px-7">
          <span className="text-xs text-slate-600">Готов свой документ? Проверьте его перед сдачей.</span>
          <button
            type="button"
            onClick={() => { skipFocusRestore.current = true; onVerify(); }}
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            <UploadCloud className="h-4 w-4" aria-hidden="true" />
            Проверить .DOCX
          </button>
        </footer>
      </div>
    </dialog>
  );
};
