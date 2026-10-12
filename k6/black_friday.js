import http from "k6/http";
import { check } from "k6";
import { Trend, Counter } from "k6/metrics";

// Settings, passed with -e NAME=value on the command line
const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const TOP_K = parseInt(__ENV.TOP_K || "5", 10); // products retrieved per question
const PROFILE = __ENV.PROFILE || "smoke";

// What Black Friday shoppers ask
const QUESTIONS = [
  "I need a waterproof jacket for hiking under £100",
  "Gift for a 10 year old who loves science",
  "Laptop for a student under £600",
  "Quiet air fryer for a small kitchen",
  "Comfortable trainers for running under £80",
  "A board game for a family Christmas",
  "Robot vacuum for a house with pets",
  "Warm winter coat under £150",
  "Headphones for the daily commute",
  "Tent for a weekend camping trip for two",
  "Best coffee machine for a beginner",
  "Lightweight hiking boots for long walks",
  "A tablet for my grandparents under £300",
  "Smart speaker for a small bedroom",
  "Yoga mat for a beginner under £40",
  "Running watch with GPS under £200",
  "Building set for a 7 year old",
  "Backpack for a student laptop",
  "A cosy duvet for winter",
  "4K TV for a small living room under £500",
  "Blender for smoothies under £60",
  "Remote-control car gift for a teenager",
  "Scarf as a Christmas gift under £30",
  "Premium noise-cancelling headphones",
  "Eco-friendly yoga mat",
  "Family tent that is easy to set up",
  "Laptop for video editing",
  "Cheap trainers for the gym",
  "Science kit for a curious 12 year old",
  "Waterproof boots for muddy dog walks",
];

// Custom metrics. The app only replies once the first word is ready,
// so k6's "waiting" time (time to first byte) is the time to first token.
const ttft = new Trend("rag_ttft", true);
const answerTime = new Trend("rag_answer_time", true);
const failedAnswers = new Counter("rag_failed_answers");

const PROFILES = {
  // Laptop check: 1 question a minute for 3 minutes
  smoke: {
    executor: "constant-arrival-rate",
    rate: 1, timeUnit: "1m", duration: "3m",
    preAllocatedVUs: 2, maxVUs: 5,
  },
  // The real test: new questions arrive at a rising rate, whether or not
  // earlier ones have been answered (an "open" model, like real traffic)
  blackfriday: {
    executor: "ramping-arrival-rate",
    startRate: 1, timeUnit: "1s",
    preAllocatedVUs: 50, maxVUs: 1000,
    stages: [
      { target: 1, duration: "2m" },  // a normal Tuesday
      { target: 4, duration: "2m" },  // midnight: the sale starts
      { target: 8, duration: "3m" },  // the rush builds
      { target: 12, duration: "3m" }, // peak rush
      { target: 16, duration: "3m" }, // beyond what the GPU can take
      { target: 0, duration: "1m" },  // the crowd goes home
    ],
  },
};

export const options = {
  scenarios: { [PROFILE]: PROFILES[PROFILE] },
  // "Broken" = 95% of shoppers don't see a first word within 2 seconds,
  // or more than 5% of requests fail. Not applied to the laptop smoke test.
  thresholds: PROFILE === "smoke" ? {} : {
    rag_ttft: ["p(95)<2000"],
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  const question = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  const res = http.post(
    `${BASE_URL}/ask`,
    JSON.stringify({ question, top_k: TOP_K }),
    {
      headers: { "Content-Type": "application/json" },
      timeout: "180s",
      tags: { top_k: String(TOP_K) },
    },
  );

  const ok = check(res, {
    "status is 200": (r) => r.status === 200,
    "got an answer": (r) => r.body && r.body.length > 20,
  });

  if (res.status === 200) {
    ttft.add(res.timings.waiting);
    answerTime.add(res.timings.duration);
  }
  if (!ok) failedAnswers.add(1);
}