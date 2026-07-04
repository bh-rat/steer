import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Callout } from 'fumadocs-ui/components/callout';
import { Card, Cards } from 'fumadocs-ui/components/card';
import { BatteryFull, Hammer } from 'lucide-react';
import type { MDXComponents } from 'mdx/types';
import type { ComponentProps, ReactNode } from 'react';

const cardIcons: Record<string, ReactNode> = {
  hammer: <Hammer />,
  'battery-full': <BatteryFull />,
};

// Shims so content written against Mintlify component names keeps working.
function NamedIconCard({
  icon,
  ...props
}: Omit<ComponentProps<typeof Card>, 'icon'> & { icon?: string }) {
  return <Card {...props} icon={icon ? cardIcons[icon] : undefined} />;
}

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    Note: (props: ComponentProps<typeof Callout>) => <Callout type="info" {...props} />,
    Warning: (props: ComponentProps<typeof Callout>) => <Callout type="warn" {...props} />,
    Card: NamedIconCard,
    CardGroup: (props: { cols?: number; children?: ReactNode }) => (
      <Cards>{props.children}</Cards>
    ),
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
