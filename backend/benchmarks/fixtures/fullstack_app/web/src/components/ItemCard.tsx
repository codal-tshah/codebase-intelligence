type Props = { name: string; onBuy: () => void };

export function ItemCard({ name, onBuy }: Props) {
  return (
    <div>
      {name} <button onClick={onBuy}>Buy</button>
    </div>
  );
}
