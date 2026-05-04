// App entry

function App() {
  return (
    <LangProvider>
      <Topbar />
      <Hero />
      <Problem />
      <CitationChain />
      <Pipeline />
      <Capabilities />
      <Numbers />
      <Demo />
      <Architecture />
      <Close />
      <Footer />
    </LangProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
