const MarkdownIt = require("markdown-it");

const md = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true
});

function markdownToPowerAppsHtml(markdown) {
    let html = md.render(markdown || "");

    // Headings
    html = html
        .replace(
            /<h1>/g,
            "<h1 style='font-size:22px;font-weight:700;margin:18px 0 10px;color:#1d2433;'>"
        )
        .replace(
            /<h2>/g,
            "<h2 style='font-size:19px;font-weight:700;margin:16px 0 8px;color:#1d2433;'>"
        )
        .replace(
            /<h3>/g,
            "<h3 style='font-size:16px;font-weight:600;margin:14px 0 7px;color:#1d2433;'>"
        );

    // Paragraphs
    html = html.replace(
        /<p>/g,
        "<p style='margin:7px 0;line-height:1.5;'>"
    );

    // Lists
    html = html
        .replace(
            /<ul>/g,
            "<ul style='margin:8px 0;padding-left:22px;list-style-type:disc;'>"
        )
        .replace(
            /<ol>/g,
            "<ol style='margin:8px 0;padding-left:22px;list-style-type:decimal;'>"
        );

    // Code blocks
    html = html
        .replace(
            /<pre>/g,
            "<pre style='background:#f4f5f7;border:1px solid #e2e5e9;border-radius:8px;padding:12px;overflow:auto;font-family:Consolas,monospace;font-size:12px;'>"
        )
        .replace(
            /<code>/g,
            "<code style='font-family:Consolas,monospace;'>"
        );

    // Tables: both horizontal AND vertical scrolling
    html = html
        .replace(
            /<table>/g,
            "<div style='max-width:100%;max-height:320px;overflow:auto;margin:12px 0;border:1px solid #dde1e6;border-radius:8px;'>" +
            "<table style='border-collapse:collapse;width:max-content;min-width:100%;font-size:13px;'>"
        )
        .replace(
            /<\/table>/g,
            "</table></div>"
        )
        .replace(
            /<th>/g,
            "<th style='padding:9px 12px;border-bottom:1px solid #d9dde3;background:#f4f6f8;text-align:left;font-weight:600;white-space:nowrap;'>"
        )
        .replace(
            /<td>/g,
            "<td style='padding:8px 12px;border-bottom:1px solid #eceef1;white-space:nowrap;'>"
        );

    return (
        "<div style='position:relative;font-family:Segoe UI,Arial,sans-serif;" +
        "font-size:14px;line-height:1.45;color:#252a32;'>" +
        html +
        "</div>"
    );
}

async function getFoundryToken() {
    const identityEndpoint = process.env.IDENTITY_ENDPOINT;
    const identityHeader = process.env.IDENTITY_HEADER;

    if (!identityEndpoint || !identityHeader) {
        throw new Error("Managed Identity is not available.");
    }

    const tokenUrl = new URL(identityEndpoint);

    tokenUrl.searchParams.set(
        "resource",
        "https://ai.azure.com"
    );

    tokenUrl.searchParams.set(
        "api-version",
        "2019-08-01"
    );

    const tokenResponse = await fetch(tokenUrl, {
        method: "GET",
        headers: {
            "X-IDENTITY-HEADER": identityHeader
        }
    });

    if (!tokenResponse.ok) {
        const text = await tokenResponse.text();

        throw new Error(
            `Managed Identity token request failed: ${tokenResponse.status} ${text}`
        );
    }

    const tokenData = await tokenResponse.json();

    return tokenData.access_token;
}


function extractAnswer(data) {
    // Some SDK/API shapes expose this directly.
    if (
        typeof data.output_text === "string" &&
        data.output_text.trim()
    ) {
        return data.output_text.trim();
    }

    // Standard Responses API structure.
    const textParts = [];

    for (const item of data.output || []) {
        if (item.type !== "message") {
            continue;
        }

        for (const content of item.content || []) {
            if (
                content.type === "output_text" &&
                typeof content.text === "string"
            ) {
                textParts.push(content.text);
            }
        }
    }

    return textParts.join("\n").trim();
}


module.exports = async function (context, req) {

    try {
        const message = req.body?.message?.trim();

        const previousResponseId =
            req.body?.previous_response_id?.trim();

        const agentSessionId =
            req.body?.agent_session_id?.trim();


        // -----------------------------
        // Validate request
        // -----------------------------

        if (!message) {
            context.res = {
                status: 400,
                headers: {
                    "Content-Type": "application/json"
                },
                body: {
                    error: "message is required"
                }
            };

            return;
        }


        // -----------------------------
        // Foundry endpoint
        // -----------------------------

        const foundryEndpoint =
            process.env.FOUNDRY_AGENT_ENDPOINT;

        if (!foundryEndpoint) {
            throw new Error(
                "FOUNDRY_AGENT_ENDPOINT is not configured."
            );
        }

        const foundryUrl =
            new URL(foundryEndpoint);

        foundryUrl.searchParams.set(
            "api-version",
            "v1"
        );


        // -----------------------------
        // Managed Identity token
        // -----------------------------

        const token =
            await getFoundryToken();


        // -----------------------------
        // Build Foundry request
        // -----------------------------

        const requestBody = {
            input: [
                {
                    role: "user",
                    content: message
                }
            ],
            stream: false
        };


        if (previousResponseId) {
            requestBody.previous_response_id =
                previousResponseId;
        }


        if (agentSessionId) {
            requestBody.agent_session_id =
                agentSessionId;
        }


        // -----------------------------
        // Call Foundry
        // -----------------------------

        const foundryResponse =
            await fetch(
                foundryUrl.toString(),
                {
                    method: "POST",
                    headers: {
                        "Authorization":
                            `Bearer ${token}`,

                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(requestBody)
                }
            );


        const rawResponse =
            await foundryResponse.text();


        if (!foundryResponse.ok) {
            throw new Error(
                `Foundry returned ${foundryResponse.status}: ${rawResponse}`
            );
        }


        const data =
            JSON.parse(rawResponse);


        // -----------------------------
        // Extract Markdown response
        // -----------------------------

        const answer =
            extractAnswer(data) ||
            "The agent completed the request but returned no text response.";


        // -----------------------------
        // Markdown -> HTML
        // -----------------------------

        const answerHtml =
            markdownToPowerAppsHtml(answer);


        // -----------------------------
        // Return to Power Apps
        // -----------------------------

        context.res = {
            status: 200,

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: {
                answer: answer,

                answer_html:
                    answerHtml,

                response_id:
                    data.id || "",

                agent_session_id:
                    data.agent_session_id || ""
            }
        };


    } catch (error) {

        context.log.error(
            "Foundry agent call failed:",
            error
        );


        const fallbackAnswer =
            "I couldn't complete that analysis. Please try again.";

        const fallbackHtml =
            "<p>I couldn't complete that analysis. Please try again.</p>";


        context.res = {
            status: 500,

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: {
                error:
                    error.message,

                answer:
                    fallbackAnswer,

                answer_html:
                    fallbackHtml,

                response_id: "",

                agent_session_id: ""
            }
        };
    }
};
