export async function GET() {
  return Response.json({
    backendUrl: process.env.ROUNDMIND_API_URL ?? "",
  });
}
