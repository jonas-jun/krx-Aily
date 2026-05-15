import Link from "next/link";

interface Props {
  name: string;
}

export function Logo({ name }: Props) {
  return (
    <Link href="/" className="flex items-center shrink-0">
      <span className="font-bold text-base tracking-tight bg-gradient-to-r from-rose-500 to-red-600 bg-clip-text text-transparent">
        {name}
      </span>
    </Link>
  );
}
