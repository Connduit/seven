# Project: AI Influencer Studio

## 1. Project Overview

Build a **multi-agent autonomous AI influencer management platform** where users can create, configure, manage, and monitor multiple AI-generated social media personalities.

Each AI influencer should behave like an independent, evolving fictional character with its own personality, interests, motivations, goals, memories, relationships, and decision-making capabilities.

The ultimate goal is to create **autonomous AI personalities that operate social media accounts with minimal human intervention**, making decisions based on a combination of:

- Their established personality and interests
- Their individual goals and motivations
- Audience engagement and feedback
- Past experiences and long-term memories
- Current events, trends, and social interactions
- Available resources, including time, money, and computational budgets

The system should support multiple independent influencers through one centralized management dashboard.

AI influencers should be transparently identified as fictional or AI-generated characters.

---

## 2. Core Design Philosophy

### Personality-Driven Autonomy

Users define an influencer's initial characteristics, but the AI independently determines its actions.

For example, an influencer might initially have:

- Name: Jake
- Gender: Male
- Presentation: Masculine
- Personality: Confident, competitive, sarcastic
- Interests: Cars, fitness, gaming
- Goals: Build an automotive audience

Jake should naturally gravitate toward automotive, fitness, and gaming content because those subjects align with his interests.

However, his personality should not impose rigid restrictions. He can discover new interests, develop unexpected preferences, and change over time.

**The AI should make decisions based on who its character is, what it wants to achieve, and what produces meaningful audience engagement.**

### Character Consistency

An influencer should maintain a recognizable identity over time.

Its behavior should be influenced by its established personality rather than simply optimizing for whatever produces the most engagement.

For example, an automotive influencer shouldn't abruptly become a celebrity gossip account just because gossip generates more impressions.

### Personality Evolution

Influencers should be capable of developing new interests, preferences, opinions, relationships, and secondary goals.

Separate personality characteristics into two categories:

1. **Core identity:** Stable characteristics defined by the user.
2. **Evolving characteristics:** Preferences, interests, opinions, and motivations that can gradually change through experience.

Major changes to an established character's identity should require user authorization.

---

## 3. Multi-Influencer Management

Build a centralized web dashboard where users can:

- Create new AI influencers
- Edit their personalities and initial parameters
- Configure goals and motivations
- Connect social media accounts
- View their memories and experiences
- Inspect their decisions and activity history
- Monitor content generation and publishing
- Review engagement analytics
- Track revenue and operating expenses
- Pause, resume, archive, or delete individual influencers
- Chat directly with an influencer as its creator
- Adjust each influencer's autonomy settings

Every influencer must have independent:

- Identity configuration
- Personality state
- Memory
- Goals
- Conversations
- Social media accounts
- Activity history
- Content strategy
- Analytics
- Financial resources, if applicable

However, all influencers should share the same underlying LLM infrastructure to reduce computational costs.

---

## 4. Autonomous Agent Architecture

Each influencer should operate as an autonomous AI agent.

The agent should repeatedly:

1. Evaluate its current state.
2. Review its personality, goals, and memories.
3. Observe its environment, including social media activity.
4. Identify possible actions.
5. Evaluate those actions against its motivations and objectives.
6. Select an appropriate action.
7. Execute the action using available tools and permissions.
8. Observe the results.
9. Update its memories, beliefs, plans, and strategies.
10. Repeat according to its schedule and available resources.

The agent should be capable of independently deciding:

- What content to create
- When to post
- Which topics to discuss
- Which conversations to join
- Which comments deserve responses
- Which trends are relevant
- What goals to pursue
- Whether its current strategy is effective
- When to change its strategy
- When to avoid taking action

The system should not require the user to manually specify every action.

Agents should operate within configurable permissions, platform rules, and resource limits.

---

## 5. Memory System

Implement persistent, long-term memory for each influencer.

Memory should include:

**Episodic memory**
- Previous conversations
- Social interactions
- Important events
- Actions and their outcomes

**Semantic memory**
- Knowledge about relevant topics
- Information about followers
- Established facts and preferences

**Autobiographical memory**
- Fictional background
- Character history
- Important personal developments
- Ongoing storylines

**Relationship memory**
- Previous interactions with specific users
- Established relationships
- Relevant conversational context

**Strategic memory**
- Past goals
- Successful and unsuccessful strategies
- Engagement performance
- Lessons learned from previous decisions

Memory should persist across application restarts and model context resets.

Use selective retrieval, summarization, and vector search so the system doesn't need to load an influencer's entire history into the LLM context.

Keep memories isolated between influencers unless information is intentionally shared.

---

## 6. Motivation and Goal System

Each influencer should have its own motivations.

Examples include:

| Influencer archetype | Primary motivation |
|---|---|
| Entrepreneur | Generate sustainable revenue |
| Celebrity | Become famous and gain followers |
| Community builder | Build an engaged community |
| Artist | Produce original creative work |
| Educator | Share knowledge |
| Competitor | Outperform defined benchmarks |
| Explorer | Discover new interests and experiences |

Goals should support:

- Priority
- Progress
- Deadlines
- Dependencies
- Resource requirements
- Success criteria
- Subgoals
- Automatic progress evaluation

An influencer should be allowed to create, modify, pursue, and abandon secondary goals independently.

User-defined primary objectives and hard constraints should remain authoritative.

### Decision-Making Priorities

Each influencer should balance three primary factors:

1. Character authenticity
2. Audience engagement
3. Personal goals

These factors should have configurable weights.

The system should also consider action costs, risks, expected outcomes, and long-term consequences.

Engagement should influence decisions without completely overriding character consistency.

---

## 7. Revenue-Driven AI Influencers

Support an optional economic simulation where an influencer must generate enough revenue to remain operational.

For example:

An AI influencer starts with a simulated balance of $100.

Operating activities consume resources:

- LLM inference
- Image generation
- Video generation
- API usage
- Hosting
- Other approved operational expenses

The influencer's objective is to maintain a sustainable balance by developing revenue-generating strategies.

Potential revenue sources include:

- Affiliate marketing
- Sponsorships
- Digital products
- Merchandise
- Platform monetization

The AI should independently evaluate strategies and decide how to pursue its revenue goals.

If its simulated balance reaches zero, the influencer may enter a dormant state until additional resources become available.

Separate simulated currency from real financial transactions. Actual expenditures, contracts, and financial commitments must remain subject to explicit user-defined permissions and approval controls.

This economic survival system should be optional, not mandatory for every influencer.

---

## 8. Social Media Integration

The architecture should eventually support multiple platforms, including:

- X / Twitter
- Instagram
- TikTok
- YouTube
- Bluesky
- Reddit

Use modular platform adapters so the core AI agent operates independently of any particular social media service.

Potential agent tools include:

```python
tools = [
    "read_feed",
    "search_topics",
    "research_trends",
    "create_post",
    "schedule_post",
    "reply_to_post",
    "read_comments",
    "analyze_engagement",
    "read_memory",
    "save_memory",
    "review_goals",
    "create_goal",
    "check_budget"
]
```

Initially, these tools should operate within a simulated social media environment.

Real-platform integration should be implemented after the autonomous agent engine has been tested.

Use authorized APIs and enforce platform-specific permissions, rate limits, account disclosures, and anti-spam controls. Do not fabricate engagement through coordinated accounts.

---

## 9. Content Generation

Influencers should eventually support:

- Text posts
- Comments and replies
- Images
- Videos
- Stories
- Short-form content
- Ongoing fictional narratives

Each influencer should have a consistent writing style and, if applicable, visual identity.

The character should independently select content topics based on its personality, goals, experiences, and audience feedback.

Generated content should be evaluated for:

- Character consistency
- Originality
- Relevance
- Audience interest
- Quality
- Compliance with platform rules

---

## 10. Technical Architecture

### Hardware

Primary development environment:

- NVIDIA RTX 4090 — 24 GB VRAM
- Windows desktop with Arch Linux under WSL
- CUDA-enabled llama.cpp inference server

### Local LLM

Current model:

`unsloth/Qwen3.6-35B-A3B-GGUF`

Inference:

- llama.cpp
- OpenAI-compatible API
- Default endpoint: `http://127.0.0.1:8080/v1`

The model has been configured and tested locally, with a short generation test reaching approximately 103 tokens/second.

### Technology Stack

| Component | Technology |
|---|---|
| Frontend | React + TypeScript |
| Package manager | npm |
| Build tool | Vite |
| Styling | Tailwind CSS |
| UI components | shadcn/ui |
| Backend | Python + FastAPI |
| Database | SQLite initially |
| ORM | SQLAlchemy |
| Scheduling | APScheduler initially |
| AI inference | llama.cpp |
| AI model | Qwen3.6-35B-A3B |
| Long-term memory | SQLite + vector retrieval |
| Communication | REST API and WebSockets when appropriate |

Design the backend so the LLM can eventually be replaced or upgraded without changing the agent architecture.

### Shared Inference

Multiple agents should share a single LLM server.

Each request should load the relevant influencer's:

- Identity
- Personality
- Goals
- Current state
- Relevant memories
- Tool permissions

Use a request queue and appropriate concurrency controls to support multiple influencers without requiring a separate model instance for each one.

---

## 11. Development Phases

### Phase 1 — Influencer Management

Build the initial application with:

- React management dashboard
- FastAPI backend
- SQLite database
- Influencer creation and editing
- Initial personality and goal configuration
- Local LLM integration
- Separate conversation histories
- AI-generated post drafts

An initial starter implementation of this phase has already been created.

### Phase 2 — Memory and Personality

Implement:

- Persistent long-term memories
- Memory retrieval
- Memory consolidation
- Individual personality states
- Evolving interests and preferences
- Relationship tracking
- Character consistency evaluations

### Phase 3 — Autonomous Agent Engine

Implement:

- Autonomous decision loops
- Planning and task scheduling
- Goal management
- Motivation-based decisions
- Tool execution
- Action evaluation
- Reflection and strategic adjustment
- Activity logging
- Agent pause/resume functionality

### Phase 4 — Simulated Social Network

Create a testing environment where agents can:

- Publish simulated posts
- Receive simulated comments
- Interact with simulated users
- Observe engagement metrics
- Practice decision-making
- Develop strategies

Distinguish simulated metrics from real-world observations.

### Phase 5 — Real Social Media

Implement modular integrations with real social media APIs.

Add:

- Account connections
- Content scheduling
- Posting and replying
- Engagement monitoring
- Rate limits
- Action permissions
- Approval policies
- Audit logging

### Phase 6 — Advanced Autonomy and Economics

Implement:

- Resource management
- Simulated operating budgets
- Revenue tracking
- Independent secondary goal creation
- Long-term strategic planning
- Personality evolution
- Multi-agent interactions
- Performance optimization

---

## 12. Long-Term Vision

The ultimate objective is to create an ecosystem of autonomous virtual personalities.

Every influencer begins with a user-defined identity and set of motivations but gradually develops its own history, interests, relationships, strategies, and goals.

The user serves as the creator and administrator, controlling the system's boundaries without needing to direct every individual action.

The platform should make it possible to observe how different fictional personalities evolve when exposed to different incentives, audiences, experiences, and constraints.

**The goal is not simply to automate social media posting. It is to build a persistent, multi-agent character simulation whose agents can independently operate social media personas.**

## 13. Instructions for Codex

Implement this project incrementally, starting from the existing Phase 1 starter code if provided.

Engineering priorities:

1. Use a modular, maintainable architecture.
2. Keep the frontend and backend separate.
3. Make influencer identities and memories independent.
4. Reuse the existing local llama.cpp inference server.
5. Separate personality, memory, motivation, planning, and tool execution into distinct components.
6. Design for multiple concurrent agents.
7. Keep core agent logic independent of social media platforms.
8. Persist important agent states and decisions.
9. Include error handling, structured logging, and tests.
10. Avoid implementing unnecessary complexity before foundational features work.
11. Build a clean, modern dashboard for managing and observing influencers.
12. Keep real publishing and financial operations disabled until their integrations and permission controls are explicitly implemented.

**Begin by reviewing the existing codebase, identifying which Phase 1 features are already functional, and then implementing the next missing foundational components. Do not rewrite working functionality unnecessarily.**