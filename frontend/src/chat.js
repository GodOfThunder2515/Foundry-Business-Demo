export const REQUEST_TIMEOUT_MS = 120_000;

const DEMO_EMAIL = "abhishek.bhosale@scatterpie.io";
const DEMO_PASSWORD = "Test@123";

export function isValidLogin(email, password) {
  return email.trim().toLowerCase() === DEMO_EMAIL && password === DEMO_PASSWORD;
}

export function buildChatRequest(message, previousResponseId = "", agentSessionId = "") {
  const trimmedMessage = message.trim();
  if (!trimmedMessage) throw new Error("Question is required.");

  return {
    message: trimmedMessage,
    previous_response_id: previousResponseId || "",
    agent_session_id: agentSessionId || "",
  };
}

export function createChatState() {
  return { chats: [], activeChatId: null };
}

function createChat(id) {
  return {
    id,
    title: "New analysis",
    messages: [],
    responseId: "",
    agentSessionId: "",
    status: "idle",
    retryQuestion: "",
  };
}

function makeTitle(question) {
  return question.length > 32 ? `${question.slice(0, 32).trimEnd()}…` : question;
}

function updateChat(state, chatId, update) {
  return {
    ...state,
    chats: state.chats.map((chat) => (chat.id === chatId ? update(chat) : chat)),
  };
}

export function chatReducer(state, action) {
  switch (action.type) {
    case "new-chat":
      return {
        ...state,
        chats: [...state.chats, createChat(action.id)],
        activeChatId: action.id,
      };
    case "select-chat":
      return state.chats.some((chat) => chat.id === action.id)
        ? { ...state, activeChatId: action.id }
        : state;
    case "submit":
      return updateChat(state, action.chatId, (chat) => {
        if (chat.status === "analyzing") return chat;
        const content = action.content.trim();
        if (!content) return chat;
        return {
          ...chat,
          title: chat.messages.length === 0 ? makeTitle(content) : chat.title,
          messages: [...chat.messages, { id: action.messageId, role: "user", content }],
          status: "analyzing",
          retryQuestion: content,
        };
      });
    case "resolve":
      return updateChat(state, action.chatId, (chat) => ({
        ...chat,
        messages: [
          ...chat.messages,
          { id: action.messageId, role: "assistant", content: action.answer },
        ],
        responseId: action.responseId || "",
        agentSessionId: action.agentSessionId || "",
        status: "idle",
      }));
    case "reject":
      return updateChat(state, action.chatId, (chat) => ({ ...chat, status: "error" }));
    case "retry":
      return updateChat(state, action.chatId, (chat) => ({ ...chat, status: "analyzing" }));
    default:
      return state;
  }
}

export async function postChat(
  { message, previousResponseId = "", agentSessionId = "" },
  { fetchImpl = fetch, timeoutMs = REQUEST_TIMEOUT_MS } = {},
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildChatRequest(message, previousResponseId, agentSessionId)),
      signal: controller.signal,
    });

    if (!response.ok) throw new Error("Function request failed");
    const data = await response.json();
    if (typeof data.answer !== "string" || !data.answer.trim()) {
      throw new Error("Function response did not include an answer");
    }

    return {
      answer: data.answer,
      responseId: data.response_id || "",
      agentSessionId: data.agent_session_id || "",
    };
  } catch {
    throw new Error("We couldn’t complete that analysis.");
  } finally {
    clearTimeout(timeout);
  }
}
