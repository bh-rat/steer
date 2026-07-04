import Link from 'next/link';
import { SteerMark } from '@/components/logo';
import { gitConfig } from '@/lib/shared';

const components = [
  {
    name: 'secrets',
    href: '/components/secrets',
    blurb: 'Per-skill credentials that never live inside the skill directory.',
  },
  {
    name: 'store',
    href: '/components/store',
    blurb: 'Per-skill SQLite: key/value, JSON documents, and raw SQL.',
  },
  {
    name: 'context',
    href: '/components/context',
    blurb: 'One command that answers "where am I, what can I use?"',
  },
  {
    name: 'flow',
    href: '/components/flow',
    blurb: 'Multi-step processes the agent cannot skip.',
  },
  {
    name: 'proc',
    href: '/components/proc',
    blurb: 'Background processes that start ready and never zombie.',
  },
  {
    name: 'learn',
    href: '/components/learn',
    blurb: 'Skills that improve from their own runs.',
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
          Agent Skills are the open standard for packaging agent capabilities,
          loaded by around 40 agent products. The format is deliberately tiny,
          so skills ship with no batteries: no credentials, no persistence, no
          context gathering, no step enforcement. Steer provides those as
          components, plus the authoring tools around the whole lifecycle.
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

      <section className="mx-auto w-full max-w-3xl px-6 pb-16 text-center">
        <h2 className="text-xl font-semibold">Author, then run</h2>
        <p className="mt-3 text-fd-muted-foreground">
          <code className="text-fd-foreground">steer new</code> scaffolds a
          spec-valid skill with components wired into its SKILL.md.{' '}
          <code className="text-fd-foreground">steer validate</code> enforces
          the spec plus hygiene checks the spec does not have.{' '}
          <code className="text-fd-foreground">steer package</code> builds an
          API-ready zip, and <code className="text-fd-foreground">steer install</code>{' '}
          puts it where your agent discovers it.
        </p>
      </section>

      <section className="mx-auto w-full max-w-4xl px-6 pb-20">
        <h2 className="text-center text-xl font-semibold">
          The standard library skills never had
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-fd-muted-foreground">
          Each component is both a Python library and a CLI subcommand, so a
          SKILL.md can use steer with no code at all.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {components.map((c) => (
            <Link
              key={c.name}
              href={c.href}
              className="rounded-xl border border-fd-border bg-fd-card p-5 text-left transition-colors hover:bg-fd-accent"
            >
              <span className="font-mono text-sm font-medium">{c.name}</span>
              <p className="mt-2 text-sm text-fd-muted-foreground">{c.blurb}</p>
            </Link>
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
