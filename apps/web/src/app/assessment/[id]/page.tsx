import { Exam } from "@/features/exam";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Exam id={id} />;
}
