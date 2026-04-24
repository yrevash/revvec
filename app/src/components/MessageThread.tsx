import { useEffect, useRef } from "react";
import type { Message } from "../lib/chatStore";
import { AnswerCard } from "./AnswerCard";
import { AnswerBody } from "./AnswerBody";

export function MessageThread({
  messages,
  onOpenSource,
}: {
  messages: Message[];
  onOpenSource?: (entityId: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  return (
    <div className="space-y-6">
      {messages.map((m) => (
        <MessageView key={m.id} message={m} onOpenSource={onOpenSource} />
      ))}
      <div ref={endRef} />
    </div>
  );
}

function MessageView({
  message,
  onOpenSource,
}: {
  message: Message;
  onOpenSource?: (entityId: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-ink text-white rounded-2xl rounded-tr-md px-4 py-2.5 text-[14.5px] leading-relaxed whitespace-pre-wrap shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant — finalized answer gets the full card (timings, citations).
  if (message.result && !message.streaming) {
    return <AnswerCard result={message.result} onOpenSource={onOpenSource} />;
  }

  // Streaming or in-flight: minimal container, no "STREAMING" chrome — let the
  // text (and the inline cursor) speak for itself.
  return (
    <div className="bg-surface-card rounded-2xl shadow-card px-7 py-6">
      <AnswerBody
        answer={message.content || ""}
        citations={[]}
        onOpenSource={onOpenSource}
        streaming={!!message.streaming}
      />
    </div>
  );
}
