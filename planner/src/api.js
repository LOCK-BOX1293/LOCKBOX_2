const API_BASE = import.meta.env.VITE_PLANNER_API_BASE ?? 'http://127.0.0.1:8788';
export async function streamPlannerTurn(payload, onEvent) {
    const response = await fetch(`${API_BASE}/api/planner/chat/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
        throw new Error(`Planner backend request failed with status ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { value, done } = await reader.read();
        if (done)
            break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';
        for (const frame of frames) {
            const line = frame
                .split('\n')
                .find((entry) => entry.startsWith('data: '));
            if (!line)
                continue;
            onEvent(JSON.parse(line.slice(6)));
        }
    }
}
