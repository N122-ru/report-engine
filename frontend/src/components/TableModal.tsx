import React, { useState } from 'react';
import { X, Plus, Trash2 } from 'lucide-react';
import { buildMarkdownTable } from '../services/tableMarkdown';

interface TableModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInsert: (markdownTable: string) => void;
}

export const TableModal: React.FC<TableModalProps> = ({ isOpen, onClose, onInsert }) => {
  const cols = 3;
  const [caption, setCaption] = useState('Параметры системы');
  const [headers, setHeaders] = useState(['Параметр', 'Значение', 'Примечание']);
  const [data, setData] = useState([
    ['Интерфейс', 'eth0', 'Основной сетевой адаптер'],
    ['IP-адрес', '192.168.1.10', 'Статический'],
    ['Шлюз', '192.168.1.1', 'Маршрутизатор'],
  ]);

  const handleHeaderChange = (cIdx: number, val: string) => {
    const next = [...headers];
    next[cIdx] = val;
    setHeaders(next);
  };

  const handleCellChange = (rIdx: number, cIdx: number, val: string) => {
    const next = [...data];
    if (!next[rIdx]) next[rIdx] = [];
    next[rIdx][cIdx] = val;
    setData(next);
  };

  const addRow = () => {
    setData([...data, new Array(cols).fill('')]);
  };

  const removeRow = (rIdx: number) => {
    if (data.length <= 1) return;
    setData(data.filter((_, i) => i !== rIdx));
  };

  const handleGenerate = () => {
    onInsert(buildMarkdownTable(caption, headers, data, cols));
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[92vh] flex flex-col rounded-2xl bg-white p-4 sm:p-6 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between border-b pb-3 shrink-0">
          <h3 className="text-base sm:text-lg font-bold text-slate-800">Конструктор таблицы по ГОСТ</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-4 space-y-4 overflow-y-auto flex-1 min-h-0">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Название таблицы (подпись)</label>
            <input
              type="text"
              value={caption}
              onChange={e => setCaption(e.target.value)}
              placeholder="Например: Исходные данные и параметры сети"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-700">
                <tr>
                  {headers.slice(0, cols).map((h, i) => (
                    <th key={i} className="border-b p-2">
                      <input
                        type="text"
                        value={h}
                        onChange={e => handleHeaderChange(i, e.target.value)}
                        placeholder={`Шапка ${i + 1}`}
                        className="w-full rounded border border-slate-300 bg-white px-2 py-1 font-semibold focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </th>
                  ))}
                  <th className="w-10 border-b p-2"></th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, rIdx) => (
                  <tr key={rIdx} className="border-b hover:bg-slate-50">
                    {new Array(cols).fill(0).map((_, cIdx) => (
                      <td key={cIdx} className="p-2">
                        <input
                          type="text"
                          value={row[cIdx] || ''}
                          onChange={e => handleCellChange(rIdx, cIdx, e.target.value)}
                          placeholder="Значение"
                          className="w-full rounded border border-slate-200 px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      </td>
                    ))}
                    <td className="p-2 text-center">
                      <button
                        onClick={() => removeRow(rIdx)}
                        className="text-slate-400 hover:text-red-500"
                        title="Удалить строку"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <button
              onClick={addRow}
              type="button"
              className="flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700"
            >
              <Plus className="h-4 w-4" /> Добавить строку
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleGenerate}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
              >
                Вставить в отчет
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
