export default {
  async fetch(request, env) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    const url = new URL(request.url);

    // Handle preflight CORS
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // Only accept POST /generate
    if (url.pathname !== "/generate" || request.method !== "POST") {
      return new Response("Not Found", { status: 404, headers: corsHeaders });
    }

    try {
      const { prompt, model = "gemini-1.5-flash" } = await request.json();
      if (!prompt) {
        return new Response(JSON.stringify({ error: "Missing prompt" }), {
          status: 400,
          headers: corsHeaders,
        });
      }

      const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

      const payload = {
        contents: [{ parts: [{ text: prompt }] }],
      };

      const resp = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": env.GEMINI_API_KEY,
        },
        body: JSON.stringify(payload),
      });

      const raw = await resp.json();

      let text = "";
      if (raw?.candidates?.length) {
        text = raw.candidates
          .map((c) => (c.content || []).map((p) => p.text || "").join(""))
          .join("\n\n");
      }

      return new Response(JSON.stringify({ text, raw }), {
        status: 200,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: String(err) }), {
        status: 500,
        headers: corsHeaders,
      });
    }
  },
};
