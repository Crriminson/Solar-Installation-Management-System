/*
  Temporary landing screen.

  Replaced when the first real feature (F01, enquiries) lands.
*/

export default function Home() {
  return (
    <main style={{ padding: "var(--space-5)" }}>
      <h1>Solar Installation Management System</h1>
      <p style={{ color: "var(--color-text-muted)" }}>
        Foundation is running. First feature: customers, sites and enquiries.
      </p>
    </main>
  );
}
