export function formatPrice(price: number | null): string {
  if (price === null || price === undefined) return "—";
  return `₩${Math.round(price).toLocaleString("ko-KR")}`;
}
