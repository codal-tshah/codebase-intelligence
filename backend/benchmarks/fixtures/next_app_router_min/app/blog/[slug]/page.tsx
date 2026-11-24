export default function BlogPost({ params }: { params: { slug: string } }) {
  return <article>{params.slug}</article>;
}