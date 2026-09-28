import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  CaretRight,
  ChatCircle,
  Copy,
  EnvelopeSimple,
  Eye,
  EyeSlash,
  List as MenuIcon,
  LockKey,
  MagnifyingGlass,
  PaperPlaneTilt,
  Plus,
  Sparkle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { chatReducer, createChatState, isValidLogin, postChat } from "./chat.js";
import { SUGGESTED_QUESTIONS, THINKING_MESSAGES } from "./content.js";

const SNAPSHOT_LABEL = "Snapshot · 15 Sep 2026";
const makeId = () => crypto.randomUUID();

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`}>
      <img src="/sp-logo.png" alt="" className="brand__mark" />
      <div>
        <strong>ScatterPie</strong>
        {!compact && <span>Luminous Operations Studio</span>}
      </div>
    </div>
  );
}

function LoginScreen({ onSuccess }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  function submit(event) {
    event.preventDefault();
    if (!isValidLogin(email, password)) {
      setError("The email or password is incorrect.");
      return;
    }
    setError("");
    onSuccess();
  }

  return (
    <main className="login-page">
      <img className="data-wave data-wave--login" src="/data-wave.png" alt="" />
      <div className="login-shell">
        <header className="login-brand">
          <Brand />
          <div className="login-brand__product">
            <strong>Manufacturing Control Tower</strong>
            <span>Operational intelligence for customer commitments</span>
          </div>
        </header>

        <section className="login-panel" aria-labelledby="login-title">
          <h1 id="login-title">Welcome back.</h1>
          <p className="login-panel__lead">Sign in to continue your analysis.</p>

          <form onSubmit={submit} noValidate>
            <label htmlFor="email">Work email</label>
            <div className="field">
              <EnvelopeSimple size={21} aria-hidden="true" />
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(error)}
                autoFocus
              />
            </div>

            <label htmlFor="password">Password</label>
            <div className="field">
              <LockKey size={21} aria-hidden="true" />
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(error)}
              />
              <button
                type="button"
                className="field__action"
                onClick={() => setShowPassword((current) => !current)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeSlash size={21} /> : <Eye size={21} />}
              </button>
            </div>

            <p className="form-error" role="alert">{error}</p>

            <button className="sign-in-button" type="submit">
              Sign in <ArrowRight size={20} weight="bold" />
            </button>
          </form>

          <div className="login-note">
            <span>Demo access only</span>
            <span>Static manufacturing snapshot · 15 Sep 2026</span>
          </div>
        </section>
      </div>
    </main>
  );
}

function Sidebar({ chats, activeChatId, open, onClose, onNewChat, onSelectChat }) {
  const history = chats.filter((chat) => chat.messages.length > 0);

  return (
    <>
      {open && <button className="drawer-backdrop" onClick={onClose} aria-label="Close navigation" />}
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`} aria-label="Analysis history">
        <div className="sidebar__topline">
          <Brand />
          <button className="icon-button sidebar__close" onClick={onClose} aria-label="Close navigation">
            <X size={20} />
          </button>
        </div>

        <button className="new-analysis" onClick={onNewChat}>
          <Plus size={20} />
          New analysis
        </button>

        <div className="sidebar__divider" />
        <p className="sidebar__label">Today</p>
        <nav className="history-list" aria-label="Chats">
          {history.length === 0 ? (
            <p className="history-empty">Your analyses will appear here.</p>
          ) : (
            history.map((chat) => (
              <button
                key={chat.id}
                className={`history-row ${chat.id === activeChatId ? "history-row--active" : ""}`}
                onClick={() => onSelectChat(chat.id)}
              >
                <ChatCircle size={19} />
                <span>{chat.title}</span>
              </button>
            ))
          )}
        </nav>

        <div className="sidebar-user">
          <span className="avatar">AB</span>
          <span>Abhishek Bhosale</span>
          <CaretRight size={17} aria-hidden="true" />
        </div>
      </aside>
    </>
  );
}

function Composer({ value, onChange, onSubmit, disabled, docked = false }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className={`composer-frame ${docked ? "composer-frame--docked" : ""}`}>
      <div className="composer">
        <Sparkle className="composer__spark" size={24} weight="fill" aria-hidden="true" />
        <textarea
          rows="1"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={docked ? "Ask a follow-up" : "Ask about orders, risk, inventory, or recovery actions"}
          aria-label="Ask the Manufacturing Control Tower"
          disabled={disabled}
        />
        <button
          type="button"
          className="send-button"
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Send question"
        >
          <PaperPlaneTilt size={21} weight="fill" />
        </button>
      </div>
    </div>
  );
}

function ThinkingState() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(
      () => setIndex((current) => (current + 1) % THINKING_MESSAGES.length),
      4000,
    );
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="thinking-state">
      <img src="/sp-logo.png" alt="" />
      <div>
        <span className="sr-only" role="status">Analysis in progress.</span>
        <p className="thinking-state__text" aria-hidden="true">{THINKING_MESSAGES[index]}</p>
        <span>This can take up to 90 seconds.</span>
      </div>
    </div>
  );
}

function MarkdownResponse({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children, ...props }) => (
          <a {...props} target="_blank" rel="noreferrer">{children}</a>
        ),
        table: ({ children }) => (
          <div className="table-scroll"><table>{children}</table></div>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function ErrorState({ onRetry, onNewChat, headingRef }) {
  return (
    <div className="error-state">
      <WarningCircle size={25} weight="fill" aria-hidden="true" />
      <div>
        <h2 ref={headingRef} tabIndex="-1">We couldn’t complete that analysis.</h2>
        <p>The request did not finish. Your question is still here, so you can safely try again.</p>
        <div className="error-state__actions">
          <button className="primary-small" onClick={onRetry}>
            <ArrowClockwise size={17} /> Try again
          </button>
          <button className="secondary-small" onClick={onNewChat}>Start a new analysis</button>
        </div>
      </div>
    </div>
  );
}

function Welcome({ composer, setComposer, onSubmit }) {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <h1 id="welcome-title">
        <span>Good morning, Abhishek.</span>
        What should we analyze today?
      </h1>
      <Composer value={composer} onChange={setComposer} onSubmit={() => onSubmit(composer)} />

      <div className="suggestions">
        <h2>Suggested analyses</h2>
        <div className="suggestions__grid">
          {SUGGESTED_QUESTIONS.map((question) => (
            <button key={question} onClick={() => onSubmit(question)}>
              <MagnifyingGlass size={20} />
              <span>{question}</span>
              <CaretRight size={17} />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function Conversation({ chat, onRetry, onNewChat, onCopy, copiedId, errorHeadingRef }) {
  return (
    <div className="conversation" role="log" aria-live="polite" aria-label="Analysis conversation">
      {chat.messages.map((message) =>
        message.role === "user" ? (
          <div className="user-message" key={message.id}>{message.content}</div>
        ) : (
          <article className="assistant-message" key={message.id}>
            <div className="assistant-message__identity">
              <img src="/sp-logo.png" alt="" />
              <span>Manufacturing Control Tower</span>
            </div>
            <div className="markdown-body"><MarkdownResponse content={message.content} /></div>
            <div className="message-actions">
              <button onClick={() => onCopy(message)} aria-label="Copy response"><Copy size={17} /></button>
              <button onClick={onRetry} aria-label="Run this analysis again"><ArrowClockwise size={17} /></button>
              {copiedId === message.id && <span role="status">Copied</span>}
            </div>
          </article>
        ),
      )}
      {chat.status === "analyzing" && <ThinkingState />}
      {chat.status === "error" && (
        <ErrorState onRetry={onRetry} onNewChat={onNewChat} headingRef={errorHeadingRef} />
      )}
    </div>
  );
}

function Workspace() {
  const [state, dispatch] = useReducer(chatReducer, undefined, () =>
    chatReducer(createChatState(), { type: "new-chat", id: makeId() }),
  );
  const [composer, setComposer] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [copiedId, setCopiedId] = useState("");
  const endRef = useRef(null);
  const errorHeadingRef = useRef(null);

  const activeChat = useMemo(
    () => state.chats.find((chat) => chat.id === state.activeChatId),
    [state.activeChatId, state.chats],
  );
  const hasConversation = Boolean(activeChat?.messages.length);

  useEffect(() => {
    if (hasConversation) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeChat?.messages.length, activeChat?.status, hasConversation]);

  useEffect(() => {
    if (activeChat?.status === "error") errorHeadingRef.current?.focus();
  }, [activeChat?.status]);

  function newAnalysis() {
    if (!activeChat || activeChat.messages.length > 0) {
      dispatch({ type: "new-chat", id: makeId() });
    }
    setComposer("");
    setDrawerOpen(false);
  }

  async function runRequest(chat, question, isRetry = false) {
    if (isRetry) dispatch({ type: "retry", chatId: chat.id });
    try {
      const result = await postChat({
        message: question,
        previousResponseId: chat.responseId,
        agentSessionId: chat.agentSessionId,
      });
      dispatch({ type: "resolve", chatId: chat.id, messageId: makeId(), ...result });
    } catch {
      dispatch({ type: "reject", chatId: chat.id });
    }
  }

  function submit(question) {
    const trimmed = question.trim();
    if (!trimmed || !activeChat || activeChat.status === "analyzing") return;

    dispatch({ type: "submit", chatId: activeChat.id, messageId: makeId(), content: trimmed });
    setComposer("");
    void runRequest(activeChat, trimmed);
  }

  function retry() {
    if (!activeChat?.retryQuestion || activeChat.status === "analyzing") return;
    void runRequest(activeChat, activeChat.retryQuestion, true);
  }

  async function copyMessage(message) {
    await navigator.clipboard.writeText(message.content);
    setCopiedId(message.id);
    setTimeout(() => setCopiedId(""), 1500);
  }

  return (
    <main className="app-shell">
      <Sidebar
        chats={state.chats}
        activeChatId={state.activeChatId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onNewChat={newAnalysis}
        onSelectChat={(id) => {
          dispatch({ type: "select-chat", id });
          setDrawerOpen(false);
          setComposer("");
        }}
      />

      <section className={`workspace ${hasConversation ? "workspace--conversation" : ""}`}>
        <img className="data-wave data-wave--workspace" src="/data-wave.png" alt="" />
        <header className="workspace-header">
          <button className="icon-button mobile-menu" onClick={() => setDrawerOpen(true)} aria-label="Open navigation">
            <MenuIcon size={21} />
          </button>
          <div>
            <h2>Manufacturing Control Tower</h2>
            <p>{SNAPSHOT_LABEL}</p>
          </div>
        </header>

        {hasConversation ? (
          <div className="conversation-layout">
            <Conversation
              chat={activeChat}
              onRetry={retry}
              onNewChat={newAnalysis}
              onCopy={copyMessage}
              copiedId={copiedId}
              errorHeadingRef={errorHeadingRef}
            />
            <div ref={endRef} />
            <div className="docked-composer">
              <Composer
                value={composer}
                onChange={setComposer}
                onSubmit={() => submit(composer)}
                disabled={activeChat.status === "analyzing"}
                docked
              />
              <p>Synthetic snapshot &nbsp;•&nbsp; Recommendations require human approval.</p>
            </div>
          </div>
        ) : (
          <Welcome composer={composer} setComposer={setComposer} onSubmit={submit} />
        )}

        {!hasConversation && (
          <footer className="workspace-footer">
            Synthetic snapshot &nbsp;•&nbsp; Recommendations require human approval.
          </footer>
        )}
      </section>
    </main>
  );
}

export function App() {
  const [authenticated, setAuthenticated] = useState(false);
  return authenticated ? <Workspace /> : <LoginScreen onSuccess={() => setAuthenticated(true)} />;
}
