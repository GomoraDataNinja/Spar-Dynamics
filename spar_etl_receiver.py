async function submitGoodsReceipt(event) {
    event.preventDefault();
    if (!currentUser) { 
        showToast('❌ Please login first', 'error'); 
        return; 
    }
    
    const poSelect = document.getElementById('grPoSelect');
    if (!poSelect.value) { 
        showToast('❌ Please select a purchase order', 'error'); 
        return; 
    }
    
    // Get the selected PO details
    const poNumber = poSelect.value;
    
    // Get items from the PO (you need to fetch PO details or store them)
    // For simplicity, we'll use a mock or you can fetch from API
    
    try {
        showToast('⏳ Receiving goods...', 'info');
        
        // Fetch PO details to get items
        const poResponse = await fetch(API_URL + '/purchase-orders');
        const poData = await poResponse.json();
        const selectedPO = poData.find(p => p.po_number === poNumber);
        
        if (!selectedPO) {
            showToast('❌ PO not found', 'error');
            return;
        }
        
        // For now, we'll use a simple receipt
        const receiptData = {
            po_number: poNumber,
            items: [
                // You need to get actual items from the PO
                // This is a placeholder - you should fetch PO lines
                { product_id: 1, product_code: "PRD001", product_name: "Sample Product", quantity: 1, unit_cost: 1.00 }
            ],
            created_by: currentUser.username
        };
        
        const response = await fetch(API_URL + '/goods-receipt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(receiptData)
        });
        
        if (response.ok) {
            const result = await response.json();
            debugLog('✅ Goods received! Receipt: ' + result.receipt_number, 'success');
            showToast('✅ Goods received! Stock updated.', 'success');
            closeModal('goodsReceiptModal');
            await loadAllData();
            loadPage('goods_receipt');
        } else {
            const error = await response.json();
            showToast('❌ Error: ' + (error.error || 'Server error'), 'error');
        }
    } catch (error) {
        debugLog('❌ Goods receipt error: ' + error.message, 'error');
        showToast('❌ Cannot connect to server', 'error');
    }
}
