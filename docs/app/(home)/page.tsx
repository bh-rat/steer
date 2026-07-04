import Link from 'next/link';
import { SteerMark } from '@/components/logo';
import { SeeItRun } from '@/components/see-it-run';
import { gitConfig } from '@/lib/shared';

const components = [
  {
    name: 'secrets',
    href: '/components/secrets',
    replaces: 'Ask the user for the API key and save it in .env.',
    blurb: 'Per-skill credentials that never live inside the skill directory.',
  },
  {
    name: 'store',
    href: '/components/store',
    replaces: 'Write your progress to /tmp/session-$$.json.',
    blurb: 'Per-skill SQLite: key/value, JSON documents, and raw SQL.',
  },
  {
    name: 'context',
    href: '/components/context',
    replaces: 'Step 0: figure out the environment before doing anything.',
    blurb: 'One command that answers "where am I, what can I use?"',
  },
  {
    name: 'flow',
    href: '/components/flow',
    replaces: 'YOU MUST COMPLETE EACH PHASE BEFORE PROCEEDING.',
    blurb: 'Multi-step processes the agent cannot skip.',
  },
  {
    name: 'proc',
    href: '/components/proc',
    replaces: 'Poll the port until the server is up. Kill it when done.',
    blurb: 'Background processes that start ready and never zombie.',
  },
  {
    name: 'learn',
    href: '/components/learn',
    replaces: "Note what failed last time so you don't repeat it.",
    blurb: 'Skills that improve from their own runs.',
  },
];

const faq = [
  {
    q: 'Why not just write the rules in SKILL.md?',
    a: 'Prose pleads; it doesn\'t enforce. A flow step with a verify condition completes only when reality matches: the file exists, the command passes, the variable is set. An agent that tries to mark steps done out of order is refused.',
  },
  {
    q: 'Do agents need steer installed to run my skill?',
    a: 'No. A skill that uses components carries its own runtime: steer new writes scripts/steer.py into the skill, a self-contained copy of exactly the chosen components, and the SKILL.md invokes it as python3 scripts/steer.py. Running the skill needs Python 3.11+, not steer. The one exception is the optional auto-learn Stop hook, which runs the installed CLI.',
  },
  {
    q: 'Does it only work with Claude Code?',
    a: 'No. Steer targets the open Agent Skills spec, and steer validate warns when a skill uses fields only Claude Code understands. Any client that loads skills can run a steer-built one.',
  },
  {
    q: 'Can I adopt it in an existing skill?',
    a: 'Yes. steer validate and steer package work on any spec skill, and components come one at a time: steer bundle --with secrets drops a runtime with just that component into the skill, and the rest of the skill stays as it was.',
  },
  {
    q: 'Is steer a registry or marketplace?',
    a: 'No. Steer sits upstream of distribution: it builds and validates what installers like npx skills ship.',
  },
  {
    q: 'What does it depend on?',
    a: 'Nothing. Python 3.11 or newer, standard library only. macOS and Linux today.',
  },
];

export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center px-6 pt-20 pb-16 text-center sm:pt-28">
        <SteerMark className="mb-6 size-12" />
        <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          The framework for building Agent Skills
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-fd-muted-foreground text-pretty">
          A SKILL.md tells your agent what to do. It can't hold credentials,
          keep state between runs, or stop the agent from skipping steps.
          Steer adds those as components, plus the tools to scaffold,
          validate, package, and install skills.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/introduction"
            className="rounded-full bg-fd-primary px-6 py-2.5 text-sm font-medium text-fd-primary-foreground transition-opacity hover:opacity-90"
          >
            Read the docs
          </Link>
          <Link
            href="/quickstart"
            className="rounded-full border border-fd-border px-6 py-2.5 text-sm font-medium transition-colors hover:bg-fd-accent"
          >
            Quickstart
          </Link>
        </div>
        <code className="mt-8 rounded-lg border border-fd-border bg-fd-secondary px-4 py-2 font-mono text-sm text-fd-secondary-foreground">
          uv tool install steer-ai
        </code>
      </section>

      <section className="mx-auto w-full max-w-5xl px-6 pb-20">
        <h2 className="mb-10 text-center text-xl font-semibold">See it run</h2>
        <SeeItRun />
      </section>

      <section className="mx-auto w-full max-w-4xl px-6 pb-20">
        <h2 className="text-center text-xl font-semibold">The components</h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-fd-muted-foreground">
          Each one replaces a pattern skills carry today as prose and fragile
          bash. Every component is a Python library and a CLI subcommand, so a
          SKILL.md can use steer with no code at all.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {components.map((c) => (
            <Link
              key={c.name}
              href={c.href}
              className="flex flex-col rounded-xl border border-fd-border bg-fd-card p-5 text-left transition-colors hover:bg-fd-accent"
            >
              <p className="border-l-2 border-fd-border pl-3 text-xs text-fd-muted-foreground italic">
                "{c.replaces}"
              </p>
              <span className="mt-4 font-mono text-sm font-medium">
                {c.name}
              </span>
              <p className="mt-2 text-sm text-fd-muted-foreground">{c.blurb}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-2xl px-6 pb-20">
        <h2 className="mb-6 text-center text-xl font-semibold">FAQ</h2>
        <div className="divide-y divide-fd-border rounded-xl border border-fd-border">
          {faq.map((item) => (
            <details key={item.q} className="group px-5 py-4">
              <summary className="cursor-pointer list-none font-medium marker:hidden">
                <span className="mr-2 inline-block text-fd-muted-foreground transition-transform group-open:rotate-90">
                  ›
                </span>
                {item.q}
              </summary>
              <p className="mt-3 pl-5 text-sm text-fd-muted-foreground">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </section>

      <footer className="border-t border-fd-border py-8">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-center gap-x-6 gap-y-2 px-6 text-sm text-fd-muted-foreground">
          <span>MIT licensed</span>
          <a
            href={`https://github.com/${gitConfig.user}/${gitConfig.repo}`}
            className="transition-colors hover:text-fd-foreground"
          >
            GitHub
          </a>
          <a
            href="https://pypi.org/project/steer-ai/"
            className="transition-colors hover:text-fd-foreground"
          >
            PyPI
          </a>
        </div>
      </footer>
    </main>
  );
}
