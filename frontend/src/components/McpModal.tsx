import React, { useState } from 'react';
import { 
  X, Copy, Check, RefreshCw, Bot, MessageSquare
} from 'lucide-react';

interface McpModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onResetToken: () => void;
}

export const McpModal: React.FC<McpModalProps> = ({
  isOpen,
  onClose,
  token,
  onResetToken
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [setupTab, setSetupTab] = useState<'agent_command' | 'direct_url' | 'cli' | 'json'>('agent_command');
  const [activeJsonTab, setActiveJsonTab] = useState<'antigravity' | 'cursor' | 'claude'>('antigravity');

  if (!isOpen) return null;

  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000';
  const sseUrl = `${origin}/api/mcp/sse?token=${token}`;

  // One-time agent setup explicitly selects the SSE transport.
  const agentSetupCommand = `Добавь MCP-сервер "report-live" с transport: "sse" и URL: ${sseUrl} в свои инструменты и подключись к нему. Если работа с этим сервером не разовая — вызови промпт agent_onboarding, самостоятельно пройди его чеклист изучения окружения и заведи локальную памятку в своей системе скиллов (сервер её не хранит). Веди раздел «Клиентские оптимизации»: дополняй его опытом после каждой сессии, не трогая серверный manifest-блок. Анкета не нужна; только если характер работы неочевиден, задай максимум один короткий вопрос: «работа с этим сервером разовая или постоянная?» Для one-shot памятку не создавай; если постоянная работа или неизвестно — продолжай без вопросов. Прочитай канонические правила из ресурса report://rules/gost732 и веди отчёт по ним: проверь get_capabilities и прочитай все страницы tools/list (следуй nextCursor). Ссылка привязана к открытой вкладке «ИИ-агент (MCP)»: если инструменты не отвечают или отчёт оказался пустым, попроси свежий URL в этом окне.`;

  const antigravityConfig = JSON.stringify({
    mcpServers: {
      "report-live": {
        serverUrl: sseUrl
      }
    }
  }, null, 2);

  const cursorConfig = JSON.stringify({
    mcpServers: {
      "report-live": {
        url: sseUrl
      }
    }
  }, null, 2);

  // Claude Code reads an entry without "type" as a stdio server and skips it.
  const claudeConfig = JSON.stringify({
    mcpServers: {
      "report-live": {
        type: "sse",
        url: sseUrl
      }
    }
  }, null, 2);

  const hermesConfigCommand = `hermes config set mcp_servers.report-live.url '${sseUrl}' && hermes config set mcp_servers.report-live.transport sse`;

  const currentJsonConfig = activeJsonTab === 'antigravity' 
    ? antigravityConfig 
    : activeJsonTab === 'cursor' 
      ? cursorConfig 
      : claudeConfig;

  const copyToClipboard = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2500);
    } catch {
      // fallback
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-2 sm:p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header. */}
        <div className="flex items-center justify-between border-b border-slate-200 px-4 sm:px-6 py-3 sm:py-4 bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-purple-600 text-white shadow-md shadow-purple-500/20">
              <Bot className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-1.5 sm:gap-2 truncate">
                <span className="truncate">ИИ-агент (MCP)</span>
                <span className="shrink-0 rounded-full bg-purple-100 text-purple-700 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
                  MCP
                </span>
              </h2>
              <p className="text-[11px] sm:text-xs text-slate-500 truncate">
                Взаимодействие ИИ-агента с отчётом через протокол MCP
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body. */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-4 sm:space-y-5 text-xs text-slate-700">
          {/* Session indicator. */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50 border border-emerald-200 p-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="relative flex h-3 w-3 shrink-0">
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </div>
              <div className="min-w-0">
                <span className="font-bold text-emerald-900 text-xs block sm:inline">Токен готов</span>
                <span className="text-[11px] text-emerald-700 sm:ml-2 font-mono break-all">
                  {token.slice(0, 16)}...
                </span>
                <span className="text-[10px] text-emerald-700 block">
                  Подключение возможно, пока открыта эта вкладка
                </span>
              </div>
            </div>
            <button
              onClick={onResetToken}
              className="flex items-center gap-1 text-[11px] font-semibold text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md transition-colors"
              title="Создать новую сессию"
            >
              <RefreshCw className="h-3 w-3" />
              <span>Новый токен</span>
            </button>
          </div>

          {/* Server connection setup. */}
          <div className="space-y-2.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <span className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-600 text-white text-[10px] font-bold">1</span>
                Параметры подключения MCP-сервера:
              </span>

              {/* Connection method tabs. */}
              <div className="flex flex-wrap rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-[11px]">
                <button
                  onClick={() => setSetupTab('agent_command')}
                  className={`px-2 sm:px-2.5 py-1 rounded-md font-bold transition-all ${
                    setupTab === 'agent_command'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Команда агенту
                </button>
                <button
                  onClick={() => setSetupTab('direct_url')}
                  className={`px-2 sm:px-2.5 py-1 rounded-md font-bold transition-all ${
                    setupTab === 'direct_url'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  SSE URL
                </button>
                <button
                  onClick={() => setSetupTab('cli')}
                  className={`px-2 sm:px-2.5 py-1 rounded-md font-bold transition-all ${
                    setupTab === 'cli'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  CLI (Hermes)
                </button>
                <button
                  onClick={() => setSetupTab('json')}
                  className={`px-2 py-1 rounded-md font-bold transition-all ${
                    setupTab === 'json'
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  JSON
                </button>
              </div>
            </div>

            {/* Agent setup command. */}
            {setupTab === 'agent_command' && (
              <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-3.5 space-y-2 animate-in fade-in duration-100">
                <p className="text-[11px] text-purple-950">
                  Инструкция для подключения агента (Antigravity, Cursor, Cline, Claude Code):
                </p>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={agentSetupCommand}
                    className="w-full rounded-lg border border-purple-200 bg-white px-3 py-2 font-mono text-[11px] text-purple-950 select-all"
                  />
                  <button
                    onClick={() => copyToClipboard(agentSetupCommand, 'agent_cmd')}
                    className="shrink-0 flex items-center justify-center gap-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white px-3.5 py-2 font-bold text-xs transition-all shadow-sm active:scale-95"
                  >
                    {copiedKey === 'agent_cmd' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'agent_cmd' ? 'Скопировано' : 'Скопировать'}</span>
                  </button>
                </div>
                <p className="text-[10px] text-purple-800">
                  Ссылка содержит токен этой вкладки. После «Новый токен» скопируйте инструкцию
                  заново и не публикуйте её.
                </p>
              </div>
            )}

            {/* Direct SSE URL. */}
            {setupTab === 'direct_url' && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 space-y-2 animate-in fade-in duration-100">
                <p className="text-[11px] text-slate-600">
                  Ссылка для конфигурации MCP (тип транспорта: <strong>SSE</strong>):
                </p>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={sseUrl}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-[11px] text-slate-800 select-all"
                  />
                  <button
                    onClick={() => copyToClipboard(sseUrl, 'url')}
                    className="shrink-0 flex items-center justify-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-900 text-white px-3.5 py-2 font-bold text-xs transition-all shadow-sm active:scale-95"
                  >
                    {copiedKey === 'url' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'url' ? 'Скопировано' : 'Скопировать URL'}</span>
                  </button>
                </div>
              </div>
            )}

            {/* Hermes CLI command. */}
            {setupTab === 'cli' && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 space-y-2 animate-in fade-in duration-100">
                <p className="text-[11px] text-slate-600">
                  Команда для консоли Hermes Agent (задаёт SSE URL и транспорт sse):
                </p>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={hermesConfigCommand}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-[11px] text-slate-800 select-all"
                  />
                  <button
                    onClick={() => copyToClipboard(hermesConfigCommand, 'hermes_cmd')}
                    className="shrink-0 flex items-center justify-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-900 text-white px-3.5 py-2 font-bold text-xs transition-all shadow-sm active:scale-95"
                  >
                    {copiedKey === 'hermes_cmd' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'hermes_cmd' ? 'Скопировано' : 'Скопировать'}</span>
                  </button>
                </div>
              </div>
            )}

            {/* Raw JSON configuration. */}
            {setupTab === 'json' && (
              <div className="space-y-2 animate-in fade-in duration-100">
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-slate-500">Конфиг для файла настроек:</span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setActiveJsonTab('antigravity')}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${activeJsonTab === 'antigravity' ? 'bg-purple-100 text-purple-700' : 'text-slate-500'}`}
                    >
                      Antigravity
                    </button>
                    <button
                      onClick={() => setActiveJsonTab('cursor')}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${activeJsonTab === 'cursor' ? 'bg-purple-100 text-purple-700' : 'text-slate-500'}`}
                    >
                      Cursor
                    </button>
                    <button
                      onClick={() => setActiveJsonTab('claude')}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${activeJsonTab === 'claude' ? 'bg-purple-100 text-purple-700' : 'text-slate-500'}`}
                    >
                      Claude
                    </button>
                  </div>
                </div>
                <div className="relative">
                  <pre className="rounded-xl border border-slate-800 bg-slate-900 p-3.5 font-mono text-[11px] text-slate-100 overflow-x-auto leading-relaxed">
                    {currentJsonConfig}
                  </pre>
                  <button
                    onClick={() => copyToClipboard(currentJsonConfig, 'json_cfg')}
                    className="absolute top-2.5 right-2.5 flex items-center gap-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 text-[10px] font-bold transition-all shadow"
                  >
                    {copiedKey === 'json_cfg' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    <span>{copiedKey === 'json_cfg' ? 'Скопировано' : 'Копировать'}</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Agent workflow instructions. */}
          <div className="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50/70 to-teal-50/30 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-white text-[10px] font-bold">2</span>
              <span className="font-bold text-emerald-950 text-xs">
                Взаимодействие с агентом в чате:
              </span>
            </div>

            <p className="text-[11px] text-emerald-900 leading-relaxed">
              Требования ГОСТ 7.32 (безличное изложение, формулы, подписи к рисункам) и инструменты работы с документом передаются агенту через MCP.
            </p>

            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase tracking-wider font-semibold text-emerald-800">
                Примеры запросов к агенту:
              </span>
              <div className="space-y-1 text-[11px]">
                <div className="rounded-lg bg-white/80 border border-emerald-200/80 px-3 py-1.5 text-slate-800 font-medium flex items-center gap-2">
                  <MessageSquare className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                  <span>«Сделай лабораторную работу №2 по сетям, вот скриншоты»</span>
                </div>
                <div className="rounded-lg bg-white/80 border border-emerald-200/80 px-3 py-1.5 text-slate-800 font-medium flex items-center gap-2">
                  <MessageSquare className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                  <span>«Напиши раздел "Ход работы" и оформи формулы расчетов»</span>
                </div>
                <div className="rounded-lg bg-white/80 border border-emerald-200/80 px-3 py-1.5 text-slate-800 font-medium flex items-center gap-2">
                  <MessageSquare className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                  <span>«Проверь оформление по ГОСТ и исправь замечания»</span>
                </div>
              </div>
            </div>

            <p className="text-[11px] text-emerald-800 flex items-center gap-1.5 pt-1 font-medium">
              <span>Изменения отображаются в предпросмотре макета А4 в реальном времени.</span>
            </p>
          </div>
        </div>

        {/* Footer. */}
        <div className="border-t border-slate-200 px-4 sm:px-6 py-2.5 sm:py-3 bg-slate-50 flex justify-end items-center">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 hover:bg-slate-900 text-white px-4 py-1.5 text-xs font-semibold transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};
