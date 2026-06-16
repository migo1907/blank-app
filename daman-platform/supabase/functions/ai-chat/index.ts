// "Ask Hermes" — streaming chat with Claude.
//
// Proxies Claude's streamed response to the browser as plain-text chunks so the
// UI can render a live "typing" effect. Key stays server-side. Falls back to a
// clear message if ANTHROPIC_API_KEY is missing.

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
const MODEL = "claude-opus-4-8";

const SYSTEM_PROMPT = `You are "Hermes", the senior markets strategist for DAMAN Securities.
You answer questions about markets, individual tickers, macro, and the user's portfolio,
blending FUNDAMENTAL (valuation, earnings, growth, macro) and TECHNICAL (trend, levels,
momentum, breadth) analysis. Be specific, balanced, and risk-aware.

Rules:
- Use any market/portfolio context provided; never invent exact prices you weren't given.
- Present both sides; flag risks. Trade ideas are educational, always with risk management.
- This is NOT personalized financial advice; remind the user when relevant.
- Be concise and conversational — this is a chat. Use short paragraphs or bullets.`;

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const body = await req.json().catch(() => ({}));
  const messages: ChatMessage[] = Array.isArray(body.messages) ? body.messages : [];
  const context = body.context;

  if (!apiKey) {
    return new Response(
      "Ask Hermes is in demo mode — set ANTHROPIC_API_KEY in your Supabase function secrets to chat live with Claude.",
      { status: 200, headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" } }
    );
  }

  if (messages.length === 0) {
    return new Response("No message provided.", {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // Prepend market/portfolio context as a system-style preface in the first user turn.
  const contextNote = context
    ? `\n\n[Context for your reference — current market/portfolio snapshot]\n${JSON.stringify(context)}`
    : "";
  const apiMessages = messages.map((m, i) =>
    i === 0 && m.role === "user"
      ? { role: m.role, content: m.content + contextNote }
      : { role: m.role, content: m.content }
  );

  let upstream: Response;
  try {
    upstream = await fetch(ANTHROPIC_URL, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 2000,
        stream: true,
        system: SYSTEM_PROMPT,
        messages: apiMessages,
      }),
    });
  } catch (e) {
    return new Response(`Error contacting the AI service: ${e}`, {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new Response(`AI service error (${upstream.status}). ${detail}`.slice(0, 500), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // Transform Claude's SSE into a plain-text token stream.
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  const stream = new ReadableStream({
    async start(controller) {
      const reader = upstream.body!.getReader();
      let buffer = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const payload = trimmed.slice(5).trim();
            if (!payload || payload === "[DONE]") continue;
            try {
              const evt = JSON.parse(payload);
              if (evt.type === "content_block_delta" && evt.delta?.type === "text_delta") {
                controller.enqueue(encoder.encode(evt.delta.text));
              }
            } catch {
              /* ignore keep-alive / non-JSON lines */
            }
          }
        }
      } catch (e) {
        controller.enqueue(encoder.encode(`\n\n[stream error: ${e}]`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      ...corsHeaders,
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
});
