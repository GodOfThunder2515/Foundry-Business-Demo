export const SUGGESTED_QUESTIONS = [
  "How exposed are we over the next two weeks, and where is the risk concentrated?",
  "Which Pune orders should my planners chase first, and why?",
  "What's the cheapest way to rescue the Pune orders due in the next seven days, and who needs to sign off?",
  "Which of our strategic customers have orders at risk of running late this week, and who should I call first?",
];

// Pool the follow-up suggestions are drawn from. Replace or extend this list
// (e.g. with ten questions); FOLLOW_UP_COUNT of them are shown after each answer.
export const FOLLOW_UP_QUESTIONS = [
  ...SUGGESTED_QUESTIONS,
  "Which plant is slipping the most compared with last week?",
  "How much revenue is stuck behind credit or customer holds right now?",
  "Is our on-time shipping getting better or worse this month, and what's driving it?",
  "How much cash is tied up in overdue invoices, and who owes us the most?",
];
export const FOLLOW_UP_COUNT = 3;

const normalize = (question) => question.trim().toLowerCase();

function shuffle(items, random) {
  const result = [...items];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [result[index], result[swap]] = [result[swap], result[index]];
  }
  return result;
}

// Randomly picks `count` distinct questions, preferring ones not already asked
// in the conversation and topping up with asked ones when the pool is small.
export function pickFollowUps(pool, count = FOLLOW_UP_COUNT, asked = [], random = Math.random) {
  const askedSet = new Set(asked.map(normalize));
  const unique = [...new Map(pool.map((question) => [normalize(question), question])).values()];
  const fresh = unique.filter((question) => !askedSet.has(normalize(question)));
  const repeats = unique.filter((question) => askedSet.has(normalize(question)));
  return [...shuffle(fresh, random), ...shuffle(repeats, random)].slice(0, count);
}

// Welcome-page greetings, one picked at random for the current time of day.
// "{name}" is replaced with the user's first name.
export const GREETINGS = {
  morning: [
    { title: "Good morning, {name}.", prompt: "Coffee's on. Where should we look first?" },
    { title: "Good morning, {name}.", prompt: "Let's get ahead of today's commitments." },
    { title: "Rise and shine, {name}.", prompt: "What needs your attention before the day starts?" },
    { title: "Morning, {name}.", prompt: "Fresh snapshot, fresh eyes. What should we check?" },
  ],
  afternoon: [
    { title: "Good afternoon, {name}.", prompt: "How's the day holding up? Let's take a look." },
    { title: "Good afternoon, {name}.", prompt: "Halfway through the day. What needs a second look?" },
    { title: "Afternoon, {name}.", prompt: "Let's catch any slips before they turn into misses." },
    { title: "Good afternoon, {name}.", prompt: "Time for a quick check-in. What should we dig into?" },
  ],
  evening: [
    { title: "Good evening, {name}.", prompt: "Let's wrap up the day. What should we review?" },
    { title: "Good evening, {name}.", prompt: "Before you sign off, what should we check on?" },
    { title: "Evening, {name}.", prompt: "Let's set up tomorrow. Where should planners start?" },
    { title: "Working late, {name}?", prompt: "Let's make it quick. What do you need to know?" },
  ],
};

// Morning 05:00–11:59, afternoon 12:00–16:59, evening 17:00–04:59.
export function timeOfDay(date = new Date()) {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  return "evening";
}

export function pickGreeting(name, date = new Date(), random = Math.random) {
  const pool = GREETINGS[timeOfDay(date)];
  const greeting = pool[Math.floor(random() * pool.length)];
  return { title: greeting.title.replace("{name}", name), prompt: greeting.prompt };
}

export const THINKING_MESSAGES = [
  "Reviewing order commitments…",
  "Checking late-order risk signals…",
  "Mapping risk concentration by site and customer…",
  "Reviewing inventory allocations and reservations…",
  "Tracing supplier, production, and quality constraints…",
  "Comparing recovery options and dependencies…",
  "Estimating service, revenue, and cost impact…",
  "Checking approval requirements…",
  "Preparing an evidence-backed response…",
];
