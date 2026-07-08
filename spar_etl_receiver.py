// ============================================
// RECEIPT FUNCTIONS
// ============================================

let currentReceiptOrder = null;

async function showReceipt(orderNumber) {
    try {
        debugLog('🧾 Fetching receipt for: ' + orderNumber, 'info');
        currentReceiptOrder = orderNumber;
        
        const response = await fetch(API_URL + '/receipt/' + orderNumber);
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'success' && data.receipt) {
                const receipt = data.receipt;
                const rewardsEarned = receipt.rewards_earned || (receipt.total_amount * 0.02);
                
                let receiptHTML = `
                    <div class="receipt-container">
                        <div class="receipt-header">
                            <h2>SPAR Dynamics 365</h2>
                            <p>Yellowcob Enterprises Pvt Ltd</p>
                            <p style="font-size:0.7rem;">123 Main Street, Harare, Zimbabwe</p>
                            <hr>
                        </div>
                        <div class="receipt-info">
                            <span class="label">Order #:</span>
                            <span>${receipt.order_number}</span>
                            <span class="label">Date:</span>
                            <span>${receipt.order_date}</span>
                            <span class="label">Time:</span>
                            <span>${receipt.order_time}</span>
                            <span class="label">Customer:</span>
                            <span>${receipt.customer_name}</span>
                        </div>
                        <hr>
                        <div style="text-align:center;padding:10px 0;color:#6B7280;">
                            <i class="fas fa-receipt"></i> Receipt generated
                        </div>
                        <div class="receipt-totals">
                            <div class="total-row">
                                <span>Total Amount:</span>
                                <span style="font-weight:700;font-size:1.2rem;">${formatCurrency(receipt.total_amount)}</span>
                            </div>
                        </div>
                        <div class="receipt-rewards">
                            ⭐ Rewards Earned: ${rewardsEarned.toFixed(2)} pts
                        </div>
                        <div class="receipt-footer">
                            <p>Thank you for shopping with SPAR!</p>
                            <p style="font-size:0.6rem;">Generated on: ${new Date().toLocaleString()}</p>
                        </div>
                    </div>
                `;
                
                document.getElementById('receiptContent').innerHTML = receiptHTML;
                openModal('receiptModal');
            } else {
                showToast('❌ Failed to load receipt', 'error');
            }
        } else {
            showToast('❌ Failed to fetch receipt', 'error');
        }
    } catch (error) {
        showToast('❌ Error: ' + error.message, 'error');
        debugLog('❌ Receipt error: ' + error.message, 'error');
    }
}
