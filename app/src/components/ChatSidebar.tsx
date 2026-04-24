import { Plus, Trash2, MessageSquare } from "lucide-react";
import type { Chat } from "../lib/chatStore";

function formatAgo(ts: number): string {
  const secs = (Date.now() - ts) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function ChatSidebar({
  chats,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  chats: Chat[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  const sorted = [...chats].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <aside className="w-[260px] flex-shrink-0 bg-surface-deep/40 border-r border-surface-deep/80 flex flex-col">
      {/* Traffic-light spacer: keeps content out from under the overlaid
          window controls, and gives the whole strip as a drag region. */}
      <div
        data-tauri-drag-region
        className="h-[38px] flex-shrink-0"
      />
      <div className="px-3 pb-3 border-b border-surface-deep/60">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2 px-3 py-2 bg-ink text-white rounded-lg text-sm font-medium hover:bg-ink-soft transition-colors"
        >
          <Plus size={14} />
          <span>New chat</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-1.5 py-2 space-y-0.5">
        {sorted.length === 0 && (
          <div className="px-3 py-8 text-center text-[11px] text-muted">
            No conversations yet
          </div>
        )}
        {sorted.map((c) => {
          const active = c.id === activeId;
          const snippet = c.messages.find((m) => m.role === "user")?.content || "";
          return (
            <div
              key={c.id}
              className={
                "group relative rounded-lg transition-colors " +
                (active ? "bg-surface-card shadow-sm" : "hover:bg-surface-card/60")
              }
            >
              <button
                onClick={() => onSelect(c.id)}
                className="w-full text-left px-2.5 py-2 pr-7"
              >
                <div className="flex items-start gap-2">
                  <MessageSquare
                    size={12}
                    className={
                      "mt-1 flex-shrink-0 " +
                      (active ? "text-accent" : "text-muted")
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <div
                      className={
                        "text-[13px] leading-snug truncate " +
                        (active ? "text-ink font-medium" : "text-ink/80")
                      }
                      title={c.title}
                    >
                      {c.title}
                    </div>
                    {snippet && !active && (
                      <div className="text-[11px] text-muted truncate mt-0.5">
                        {snippet}
                      </div>
                    )}
                    <div className="text-[10px] text-muted font-mono mt-0.5">
                      {formatAgo(c.updatedAt)} · {c.persona.replace("_", " ")}
                    </div>
                  </div>
                </div>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(c.id);
                }}
                className="absolute top-1.5 right-1.5 p-1.5 rounded-md opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-red-100 hover:text-red-700 text-muted transition-all"
                title="delete conversation"
                aria-label="delete conversation"
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
      </div>
      <div className="px-3 py-2 border-t border-surface-deep/60 text-[10px] text-muted font-mono">
        {sorted.length} {sorted.length === 1 ? "chat" : "chats"} · local only
      </div>
    </aside>
  );
}
