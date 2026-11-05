/** Incremental Server-Sent Events parser (multi-line `data:` fields are joined with "\n"). */
export type SseEvent = { event: string; data: string };

export function createSseParser(onEvent: (e: SseEvent) => void) {
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  const dispatch = () => {
    if (data.length) onEvent({ event, data: data.join("\n") });
    event = "message";
    data = [];
  };

  return {
    push(chunk: string) {
      buffer += chunk;
      let idx: number;
      while ((idx = buffer.search(/\r?\n/)) >= 0) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + (buffer[idx] === "\r" ? 2 : 1));
        if (line === "") dispatch();
        else if (line.startsWith(":")) continue;
        else {
          const colon = line.indexOf(":");
          const field = colon < 0 ? line : line.slice(0, colon);
          let value = colon < 0 ? "" : line.slice(colon + 1);
          if (value.startsWith(" ")) value = value.slice(1);
          if (field === "event") event = value || "message";
          else if (field === "data") data.push(value);
        }
      }
    },
    end() {
      if (buffer) this.push("\n");
      dispatch();
    },
  };
}
