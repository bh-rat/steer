'use client';

import { useEffect, useRef, useState } from 'react';

type Line = { kind: 'cmd' | 'out' | 'ok' | 'err'; text: string };

type Step = {
  id: string;
  title: string;
  desc: string;
  lines: Line[];
};

// Terminal contents are real `steer` output, captured verbatim.
const steps: Step[] = [
  {
    id: 'scaffold',
    title: 'Scaffold',
    desc: 'One command generates a spec-valid skill with the components wired into its SKILL.md.',
    lines: [
      {
        kind: 'cmd',
        text: 'steer new payment-report --with secrets,context,flow,learn \\\n    --steps fetch,review,report --scripts',
      },
      { kind: 'out', text: 'Created skill at payment-report' },
      { kind: 'out', text: '  + SKILL.md' },
      { kind: 'out', text: '  + flow.toml' },
      { kind: 'out', text: '  + scripts/example.py' },
      { kind: 'out', text: '' },
      { kind: 'ok', text: 'Validation: clean' },
    ],
  },
  {
    id: 'enforce',
    title: 'Enforce',
    desc: 'Flow steps verify against reality. Marking a step done out of order is refused, not discouraged.',
    lines: [
      { kind: 'cmd', text: 'steer flow status' },
      { kind: 'out', text: '  PAYMENT-REPORT WORKFLOW' },
      { kind: 'out', text: '  Progress: 0/3 steps  ● fetch  ○ review  ○ report' },
      { kind: 'out', text: '' },
      { kind: 'out', text: '  ▸ Next: fetch' },
      { kind: 'cmd', text: 'steer flow done review' },
      {
        kind: 'err',
        text: "Not so fast: Step 'review' is blocked. Complete these first: fetch",
      },
    ],
  },
  {
    id: 'secrets',
    title: 'Hand off secrets',
    desc: 'The agent gets the exact command to relay to the human. Values never enter the chat or the skill directory.',
    lines: [
      { kind: 'cmd', text: 'steer secrets check PAYMENT_REPORT_API_KEY' },
      {
        kind: 'out',
        text: "Secret 'PAYMENT_REPORT_API_KEY' is not set for skill 'payment-report'.",
      },
      { kind: 'out', text: 'Ask the user to provide it, then store it with:' },
      {
        kind: 'out',
        text: '  steer secrets set PAYMENT_REPORT_API_KEY --skill payment-report',
      },
    ],
  },
  {
    id: 'learn',
    title: 'Learn',
    desc: 'Lessons recorded mid-run come back as a digest at the start of the next one.',
    lines: [
      {
        kind: 'cmd',
        text: 'steer learn note "Use the EU endpoint for EU accounts" --kind correction',
      },
      { kind: 'ok', text: '✓ Lesson recorded (id 1)' },
      { kind: 'cmd', text: 'steer learn show' },
      { kind: 'out', text: '## Lessons from previous runs (payment-report)' },
      { kind: 'out', text: '- [1] Use the EU endpoint for EU accounts' },
      { kind: 'out', text: '- [2] Validate ledger columns before summing' },
    ],
  },
];

function Terminal({ lines }: { lines: Line[] }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-fd-border bg-zinc-950 p-5 font-mono text-[13px] leading-relaxed text-zinc-300">
      {lines.map((line, i) => (
        <div key={i}>
          {line.kind === 'cmd' ? (
            <span>
              <span className="select-none text-emerald-400">$ </span>
              <span className="text-zinc-100">{line.text}</span>
            </span>
          ) : line.kind === 'ok' ? (
            <span className="text-emerald-400">{line.text}</span>
          ) : line.kind === 'err' ? (
            <span className="text-red-400">{line.text}</span>
          ) : (
            <span>{line.text || ' '}</span>
          )}
        </div>
      ))}
    </pre>
  );
}

export function SeeItRun() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = refs.current.indexOf(entry.target as HTMLDivElement);
          if (index !== -1) setActive(index);
        }
      },
      { rootMargin: '-40% 0px -40% 0px' },
    );
    for (const el of refs.current) if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="grid gap-10 md:grid-cols-[1fr_1.5fr]">
      <ol className="sticky top-28 hidden self-start md:block">
        {steps.map((step, i) => (
          <li
            key={step.id}
            className={`border-l-2 py-3 pl-5 transition-colors ${
              i === active
                ? 'border-fd-primary'
                : 'border-fd-border text-fd-muted-foreground'
            }`}
          >
            <p className="font-medium">{step.title}</p>
            <p
              className={`mt-1 text-sm ${
                i === active ? 'text-fd-muted-foreground' : 'opacity-60'
              }`}
            >
              {step.desc}
            </p>
          </li>
        ))}
      </ol>
      <div className="flex flex-col gap-10">
        {steps.map((step, i) => (
          <div
            key={step.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
          >
            <p className="mb-2 font-medium md:hidden">{step.title}</p>
            <p className="mb-3 text-sm text-fd-muted-foreground md:hidden">
              {step.desc}
            </p>
            <Terminal lines={step.lines} />
          </div>
        ))}
      </div>
    </div>
  );
}
