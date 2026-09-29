import test from "node:test";
import assert from "node:assert/strict";

import {
  REQUEST_TIMEOUT_MS,
  buildChatRequest,
  chatReducer,
  createChatState,
  findDemoUser,
  isValidLogin,
  postChat,
} from "../src/chat.js";
import {
  FOLLOW_UP_COUNT,
  FOLLOW_UP_QUESTIONS,
  GREETINGS,
  SUGGESTED_QUESTIONS,
  THINKING_MESSAGES,
  pickFollowUps,
  pickGreeting,
  timeOfDay,
} from "../src/content.js";

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

test("each demo account signs in with the shared password and carries its own name", () => {
  const cases = [
    ["abhishek.bhosale@scatterpie.io", "Abhishek", "Abhishek Bhosale", "AB"],
    ["gaurav@ScatterPie.io", "Gaurav", "Gaurav", "G"],
    ["manish.parmar@scatterpie.io", "Manish", "Manish Parmar", "MP"],
    ["ashish@scatterpie.io", "Ashish", "Ashish", "A"],
  ];
  for (const [email, firstName, fullName, initials] of cases) {
    assert.deepEqual(findDemoUser(`  ${email.toUpperCase()} `, "Test@123"), { firstName, fullName, initials });
    assert.equal(findDemoUser(email, "test@123"), null);
  }
  assert.equal(findDemoUser("nobody@scatterpie.io", "Test@123"), null);
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

test("follow-ups draw three distinct questions from the configurable pool", () => {
  assert.equal(FOLLOW_UP_COUNT, 3);
  assert.equal(FOLLOW_UP_QUESTIONS.length, 8);
  assert.equal(new Set(FOLLOW_UP_QUESTIONS).size, FOLLOW_UP_QUESTIONS.length);
  assert.ok(SUGGESTED_QUESTIONS.every((question) => FOLLOW_UP_QUESTIONS.includes(question)));
  assert.ok(FOLLOW_UP_QUESTIONS.includes("How much cash is tied up in overdue invoices, and who owes us the most?"));

  const picked = pickFollowUps(FOLLOW_UP_QUESTIONS);
  assert.equal(picked.length, 3);
  assert.equal(new Set(picked).size, 3);
  assert.ok(picked.every((question) => FOLLOW_UP_QUESTIONS.includes(question)));
});

test("follow-ups prefer questions not yet asked and scale to a larger pool", () => {
  const pool = Array.from({ length: 10 }, (_, index) => `Question ${index + 1}?`);
  const asked = [" question 1? ", "Question 2?"];
  for (let run = 0; run < 25; run += 1) {
    const picked = pickFollowUps(pool, 3, asked);
    assert.equal(new Set(picked).size, 3);
    assert.ok(picked.every((question) => !["Question 1?", "Question 2?"].includes(question)));
  }

  const small = ["A?", "B?", "C?", "D?"];
  const fallback = pickFollowUps(small, 3, ["A?", "B?"], () => 0);
  assert.equal(fallback.length, 3);
  assert.deepEqual(fallback.slice(0, 2).sort(), ["C?", "D?"]);
  assert.ok(["A?", "B?"].includes(fallback[2]));
});

test("time of day splits into morning, afternoon and evening", () => {
  const at = (hour) => timeOfDay(new Date(2026, 8, 28, hour, 30));
  assert.equal(at(4), "evening");
  assert.equal(at(5), "morning");
  assert.equal(at(11), "morning");
  assert.equal(at(12), "afternoon");
  assert.equal(at(16), "afternoon");
  assert.equal(at(17), "evening");
  assert.equal(at(23), "evening");
});

test("greeting is drawn from the current time-of-day pool with the name filled in", () => {
  for (const period of ["morning", "afternoon", "evening"]) {
    assert.equal(GREETINGS[period].length, 4);
  }

  const morning = new Date(2026, 8, 28, 8, 0);
  assert.deepEqual(pickGreeting("Abhishek", morning, () => 0), {
    title: "Good morning, Abhishek.",
    prompt: "Coffee's on. Where should we look first?",
  });

  const late = pickGreeting("Abhishek", new Date(2026, 8, 28, 23, 0), () => 0.99);
  assert.deepEqual(late, {
    title: "Working late, Abhishek?",
    prompt: "Let's make it quick. What do you need to know?",
  });
});
