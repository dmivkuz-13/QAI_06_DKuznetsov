import { Plugin } from "@opencode/plugin"

export default Plugin.define({
    id: "confluence",

    async setup(ctx) {
        await ctx.tool.transform((editor) => {
            editor.add({
                name: "confluence_get_page",
                description: "Получить страницу Confluence по pageId",
                input: {
                    type: "object",
                    properties: {
                        pageId: { type: "string" },
                    },
                    required: ["pageId"],
                    additionalProperties: false,
                },
                execute: async (input, { signal }) => {
                    const { pageId } = input as { pageId: string }

                    const baseUrl = process.env.CONFLUENCE_URL?.trim().replace(/\/+$/, "")
                    const email = process.env.CONFLUENCE_EMAIL?.trim()
                    const token = process.env.CONFLUENCE_API_TOKEN?.trim()

                    if (!baseUrl || !email || !token) {
                        throw new Error("Не заданы переменные окружения Confluence: CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN")
                    }

                    const auth = Buffer.from(`${email}:${token}`).toString("base64")
                    const apiUrl = `${baseUrl}/wiki/api/v2/pages/${pageId}?body-format=storage`

                    const timeoutMs = parseInt(process.env.CONFLUENCE_TIMEOUT || "30", 10) * 1000
                    const timeoutController = new AbortController()
                    const timer = setTimeout(() => timeoutController.abort(), timeoutMs)

                    try {
                        // Комбинируем сигналы: пользовательский и тайм-аут
                        const combinedSignal = signal
                        signal.addEventListener("abort", () => timeoutController.abort(), { once: true })

                        const response = await fetch(apiUrl, {
                            method: "GET",
                            signal: timeoutController.signal,
                            headers: {
                                Authorization: `Basic ${auth}`,
                                Accept: "application/json",
                            },
                        })

                        if (!response.ok) {
                            let errorBody = ""
                            try {
                                errorBody = await response.text()
                            } catch {
                                // ignore
                            }
                            const message = `Confluence API error: ${response.status} ${response.statusText}`
                            throw new Error(errorBody ? `${message} — ${errorBody}` : message)
                        }

                        return { content: await response.text() }
                    } finally {
                        clearTimeout(timer)
                    }
                },
            })
        })
    },
})
