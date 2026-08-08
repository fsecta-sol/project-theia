# Theia Initial Seed Questions

> Run these **once** on first activation.  
> After completion, Theia switches to auto-discovery mode (red-string graph).

## The 10 Seed Questions

1. **What is Solana?** Who created it, why PoH, and how does it differ from Ethereum in throughput/finality/fees?

2. **How does the Solana account model work?** What is the difference between Account and Wallet, and what is a PDA?

3. **What happens in a Solana transaction lifecycle?** Step by step from user click to block finalization — blockhash, fee payer, compute budget.

4. **How are SPL tokens created and transferred?** What are Mint Account, ATA, and Token Program roles?

5. **What is pump.fun and how does its bonding curve work?** What triggers graduation to Raydium and why does this matter?

6. **How does a Constant Product Market Maker (CPMM) like Raydium work?** How is price determined and what is slippage?

7. **What is the difference between LP burn and LP lock?** Why is this critical for rug-pull screening?

8. **What are mint authority and freeze authority?** What risks remain if these are not revoked?

9. **What is MEV on Solana?** How do Jito bundles work and why can Theia not compete on speed?

10. **What are the common rug-pull and honeypot patterns?** How does each manifest on-chain and in market data?

---

## How to Use

- On first boot: Theia reads this file, queues 10 `theia-learn-solana` tasks in order.
- Each cycle: research web (via `theia-webscraper`) + on-chain (via `theia-chainrpc`), verify sources, write to `00-Inbox/_knowledge/`.
- After question 10: delete or rename this file. Theia switches to auto-discovery from `knowledge_links` graph.
