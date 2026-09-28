import test from "node:test";
import assert from "node:assert/strict";

import {
  REQUEST_TIMEOUT_MS,
  buildChatRequest,
  chatReducer,
  createChatState,
  isValidLogin,
  postChat,
} from "../src/chat.js";
import { SUGGESTED_QUESTIONS, THINKING_MESSAGES } from "../src/content.js";

const addChat = (state, id) => chatReducer(state, { type: "new-chat", id });

test("approved recommendations and thinking copy remain exact", () => {
  assert.deepEqual(SUGGESTED_QUESTIONS, [
    "How exposed are we over the next two weeks, and where is the risk concentrated?",
    "Which Pune orders should my planners chase first, and why?",
    "What's the cheapest way to rescue the Pune orders due in the next seven days, and who needs to sign off?",
    "Which of our strategic customers have orders at risk of running late this week, and who should I call first?",
  ]);
  assert.equal(THINKING_MESSAGES.length, 9);
  assert.equal(THINKING_MESSAGES[0], "Reviewing order commitments…");
  assert.equal(THINKING_MESSAGES.at(-1), "Preparing an evidence-backed response…");
});

test("demo login accepts only the configured credentials", () => {
  assert.equal(isValidLogin("abhishek.bhosale@scatterpie.io", "Test@123"), true);
  assert.equal(isValidLogin("abhishek.bhosale@scatterpie.io", "wrong"), false);
  assert.equal(isValidLogin("someone@example.com", "Test@123"), false);
});

test("first-turn request sends blank conversation identifiers", () => {
  assert.deepEqual(buildChatRequest("  Show risk  ", "", ""), {
    message: "Show risk",
    previous_response_id: "",
    agent_session_id: "",
  });
  assert.throws(() => buildChatRequest("   ", "", ""), /Question is required/);
});

test("follow-up request sends the latest conversation identifiers", () => {
  assert.deepEqual(buildChatRequest("What changed?", "resp-1", "session-1"), {
    message: "What changed?",
    previous_response_id: "resp-1",
    agent_session_id: "session-1",
  });
});

test("new chats start blank and keep other chat identifiers intact", () => {
  let state = addChat(createChatState(), "chat-1");
  state = chatReducer(state, {
    type: "submit",
    chatId: "chat-1",
    messageId: "message-1",
    content: "How exposed are we?",
  });
  state = chatReducer(state, {
    type: "resolve",
    chatId: "chat-1",
    messageId: "message-2",
    answer: "Grounded answer",
    responseId: "resp-1",
    agentSessionId: "session-1",
  });
  state = addChat(state, "chat-2");

  assert.equal(state.activeChatId, "chat-2");
  assert.equal(state.chats[0].responseId, "resp-1");
  assert.equal(state.chats[1].responseId, "");
  assert.equal(state.chats[1].agentSessionId, "");
});

test("late responses update their originating chat without changing selection", () => {
  let state = addChat(createChatState(), "chat-1");
  state = chatReducer(state, {
    type: "submit",
    chatId: "chat-1",
    messageId: "message-1",
    content: "First question",
  });
  state = addChat(state, "chat-2");
  state = chatReducer(state, {
    type: "resolve",
    chatId: "chat-1",
    messageId: "message-2",
    answer: "Late answer",
    responseId: "resp-late",
    agentSessionId: "session-late",
  });

  const origin = state.chats.find((chat) => chat.id === "chat-1");
  assert.equal(state.activeChatId, "chat-2");
  assert.equal(origin.messages.at(-1).content, "Late answer");
  assert.equal(origin.responseId, "resp-late");
  assert.equal(origin.agentSessionId, "session-late");
});

test("failed requests preserve a safe retry state without backend details", () => {
  let state = addChat(createChatState(), "chat-1");
  state = chatReducer(state, {
    type: "submit",
    chatId: "chat-1",
    messageId: "message-1",
    content: "Question to retry",
  });
  state = chatReducer(state, {
    type: "reject",
    chatId: "chat-1",
    rawError: "Foundry returned 500 with secret details",
  });

  const chat = state.chats[0];
  assert.equal(chat.status, "error");
  assert.equal(chat.retryQuestion, "Question to retry");
  assert.equal(JSON.stringify(chat).includes("secret details"), false);
});

test("retry returns the failed chat to analyzing without duplicating the question", () => {
  let state = addChat(createChatState(), "chat-1");
  state = chatReducer(state, {
    type: "submit",
    chatId: "chat-1",
    messageId: "message-1",
    content: "Question to retry",
  });
  state = chatReducer(state, { type: "reject", chatId: "chat-1" });
  state = chatReducer(state, { type: "retry", chatId: "chat-1" });

  assert.equal(state.chats[0].status, "analyzing");
  assert.equal(state.chats[0].messages.length, 1);
  assert.equal(state.chats[0].retryQuestion, "Question to retry");
});

test("completed chats retain their last question for run-again", () => {
  let state = addChat(createChatState(), "chat-1");
  state = chatReducer(state, {
    type: "submit",
    chatId: "chat-1",
    messageId: "message-1",
    content: "Question to run again",
  });
  state = chatReducer(state, {
    type: "resolve",
    chatId: "chat-1",
    messageId: "message-2",
    answer: "Grounded answer",
    responseId: "resp-1",
    agentSessionId: "session-1",
  });

  assert.equal(state.chats[0].retryQuestion, "Question to run again");
});

test("postChat maps the Function request and response contract", async () => {
  let captured;
  const fetchImpl = async (url, init) => {
    captured = { url, init };
    return {
      ok: true,
      json: async () => ({
        answer: "**Result**",
        answer_html: "<strong>ignored</strong>",
        response_id: "resp-2",
        agent_session_id: "session-2",
      }),
    };
  };

  const result = await postChat(
    { message: "Follow up", previousResponseId: "resp-1", agentSessionId: "session-1" },
    { fetchImpl },
  );

  assert.equal(REQUEST_TIMEOUT_MS, 120_000);
  assert.equal(captured.url, "/api/chat");
  assert.equal(captured.init.method, "POST");
  assert.deepEqual(JSON.parse(captured.init.body), {
    message: "Follow up",
    previous_response_id: "resp-1",
    agent_session_id: "session-1",
  });
  assert.deepEqual(result, {
    answer: "**Result**",
    responseId: "resp-2",
    agentSessionId: "session-2",
  });
});

test("postChat returns only a safe client error", async () => {
  const fetchImpl = async () => ({
    ok: false,
    json: async () => ({ error: "private stack trace" }),
  });

  await assert.rejects(
    postChat({ message: "Question" }, { fetchImpl }),
    (error) => error.message === "We couldn’t complete that analysis.",
  );
});
