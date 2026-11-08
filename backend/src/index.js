const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });

function unauthorized() {
  return json({ error: "Unauthorized" }, 401);
}

function validTimezone(timezone) {
  if (typeof timezone !== "string" || timezone.length > 100) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: timezone });
    return true;
  } catch {
    return false;
  }
}

async function verifyDiscordRequest(request, body, publicKeyHex) {
  const signature = request.headers.get("x-signature-ed25519");
  const timestamp = request.headers.get("x-signature-timestamp");
  if (!signature || !timestamp || !/^[0-9a-f]{128}$/i.test(signature)) return false;
  if (!/^[0-9a-f]{64}$/i.test(publicKeyHex || "")) return false;

  const hexToBytes = (hex) =>
    new Uint8Array(hex.match(/.{2}/g).map((byte) => parseInt(byte, 16)));

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      hexToBytes(publicKeyHex),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return crypto.subtle.verify(
      { name: "Ed25519" },
      key,
      hexToBytes(signature),
      new TextEncoder().encode(timestamp + body),
    );
  } catch {
    return false;
  }
}

async function handleDiscordInteraction(request, env, bodyText) {
  if (!(await verifyDiscordRequest(request, bodyText, env.DISCORD_PUBLIC_KEY))) {
    return unauthorized();
  }

  const interaction = JSON.parse(bodyText);
  // Discord PING
  if (interaction.type === 1) return json({ type: 1 });

  // APPLICATION_COMMAND
  if (interaction.type === 2 && interaction.data?.name === "set_timezone") {
    const timezone = interaction.data.options?.find((o) => o.name === "timezone")?.value;
    if (!validTimezone(timezone)) {
      return json({
        type: 4,
        data: { content: "Please provide a valid IANA timezone, e.g. Europe/Paris.", flags: 64 },
      });
    }

    const guildId = interaction.guild_id;
    const userId = interaction.member?.user?.id || interaction.user?.id;
    if (!guildId || !userId) {
      return json({
        type: 4,
        data: { content: "Use this command inside a server.", flags: 64 },
      });
    }

    await env.DB.prepare(
      `INSERT INTO user_timezones (guild_id, user_id, timezone, updated_at)
       VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
       ON CONFLICT(guild_id, user_id) DO UPDATE SET
         timezone = excluded.timezone,
         updated_at = excluded.updated_at`,
    ).bind(guildId, userId, timezone).run();

    return json({
      type: 4,
      data: { content: `Your timezone is now set to **${timezone}**.`, flags: 64 },
    });
  }

  return json({ type: 4, data: { content: "Unsupported command.", flags: 64 } });
}

async function handleApi(request, env, url) {
  const auth = request.headers.get("authorization");
  if (!env.API_TOKEN || auth !== `Bearer ${env.API_TOKEN}`) return unauthorized();

  if (url.pathname === "/api/messages" && request.method === "GET") {
    const guildId = url.searchParams.get("guild_id");
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 50), 1), 100);
    if (!guildId) return json({ error: "guild_id is required" }, 400);

    const result = await env.DB.prepare(
      `SELECT m.message_id, m.guild_id, m.channel_id, m.user_id, m.username,
              m.content, m.created_at, m.edited_at, tz.timezone
       FROM messages m
       LEFT JOIN user_timezones tz
         ON tz.guild_id = m.guild_id AND tz.user_id = m.user_id
       WHERE m.guild_id = ? AND m.deleted_at IS NULL
       ORDER BY m.created_at DESC LIMIT ?`,
    ).bind(guildId, limit).all();

    return json({ messages: result.results || [] });
  }

  if (url.pathname === "/api/messages" && request.method === "POST") {
    const payload = await request.json();
    const required = ["message_id", "guild_id", "channel_id", "user_id", "username", "created_at"];
    if (required.some((key) => typeof payload[key] !== "string" || !payload[key])) {
      return json({ error: "Missing required message fields" }, 400);
    }
    if (payload.content != null && typeof payload.content !== "string") {
      return json({ error: "content must be a string" }, 400);
    }

    await env.DB.prepare(
      `INSERT INTO messages
       (message_id, guild_id, channel_id, user_id, username, content, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(message_id) DO UPDATE SET
         content = excluded.content,
         username = excluded.username`,
    ).bind(
      payload.message_id, payload.guild_id, payload.channel_id,
      payload.user_id, payload.username, payload.content || "", payload.created_at,
    ).run();

    return json({ ok: true }, 201);
  }

  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/health" && request.method === "GET") {
        return json({ ok: true, service: "tzone-api" });
      }
      if (url.pathname === "/discord/interactions" && request.method === "POST") {
        const bodyText = await request.text();
        return await handleDiscordInteraction(request, env, bodyText);
      }
      if (url.pathname.startsWith("/api/")) {
        return await handleApi(request, env, url);
      }
      return json({ error: "Not found" }, 404);
    } catch (error) {
      console.error("Tzone request failed:", error);
      return json({ error: "Internal server error" }, 500);
    }
  },
};
